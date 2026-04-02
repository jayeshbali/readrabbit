"""
aggregator_tap.py — Layer 3: Aggregator taps (HN, Lobsters, Pinboard, Reddit).

For each configured aggregator:
  1. Fetch top/hot stories from the aggregator API
  2. Persist discoveries to aggregator_discoveries table
  3. Apply hard gates + quality scoring
  4. Extract full article content via trafilatura (readability-lxml fallback)
  5. Persist new articles with aggregator_score to articles table
  6. Generate embeddings via enrich_article_embedding()

Returns a stats dict: {sources_tapped, discoveries_found, new_articles, skipped, errors}
"""

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import Article, Source
from quality_pipeline import (
    compute_quality_score,
    enrich_article_embedding,
    passes_hard_gates,
)

logger = logging.getLogger(__name__)

# HTTP timeout for all aggregator fetches
FETCH_TIMEOUT = 15
# Max discoveries to process per aggregator per run
MAX_DISCOVERIES_PER_SOURCE = 50
# User-agent
UA = "ReadRabbit/1.0 (aggregator tap; +https://readrabbit.app)"

# Reddit subreddits to tap
REDDIT_SUBREDDITS = [
    "programming",
    "technology",
    "MachineLearning",
    "science",
    "worldnews",
]


def _domain_from_url(url: str) -> Optional[str]:
    """Extract bare domain from URL, stripping www."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return None
        host = parsed.netloc.lower().split(":")[0]
        if host.startswith("www."):
            host = host[4:]
        return host if host else None
    except Exception:
        return None


def _extract_content(url: str) -> tuple[Optional[str], Optional[str], int]:
    """
    Fetch and extract full article text from a URL.
    Returns (html_content, plain_text, word_count).
    Tries trafilatura first, falls back to readability-lxml.
    """
    try:
        response = httpx.get(
            url,
            follow_redirects=True,
            timeout=FETCH_TIMEOUT,
            headers={"User-Agent": UA},
        )
        response.raise_for_status()
        raw_html = response.text
    except Exception as exc:
        logger.debug("Failed to fetch %s: %s", url, exc)
        return None, None, 0

    plain_text = None

    try:
        import trafilatura
        plain_text = trafilatura.extract(
            raw_html,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )
    except Exception:
        pass

    if not plain_text:
        try:
            from readability import Document as ReadabilityDoc
            doc = ReadabilityDoc(raw_html)
            summary_html = doc.summary()
            plain_text = re.sub(r"<[^>]+>", " ", summary_html)
        except Exception:
            pass

    if not plain_text:
        return raw_html, None, 0

    word_count = len(plain_text.split())
    return raw_html, plain_text, word_count


def _persist_discovery(
    db: Session,
    url: str,
    title: Optional[str],
    aggregator: str,
    score: int,
    comment_count: int,
) -> Optional[str]:
    """
    Insert or update an aggregator_discoveries row.
    Returns the discovery ID on success, None on error.
    Uses ON CONFLICT (url, aggregator) to keep highest score.
    """
    discovery_id = str(uuid.uuid4())
    try:
        result = db.execute(
            text(
                """
                INSERT INTO aggregator_discoveries
                    (id, url, title, aggregator, score, comment_count, discovered_at)
                VALUES
                    (:id, :url, :title, :aggregator, :score, :comment_count, :discovered_at)
                ON CONFLICT (url, aggregator) DO UPDATE
                    SET score = GREATEST(aggregator_discoveries.score, EXCLUDED.score),
                        comment_count = GREATEST(aggregator_discoveries.comment_count, EXCLUDED.comment_count),
                        title = COALESCE(aggregator_discoveries.title, EXCLUDED.title)
                RETURNING id
                """
            ),
            {
                "id": discovery_id,
                "url": url,
                "title": title[:500] if title else None,
                "aggregator": aggregator,
                "score": score,
                "comment_count": comment_count,
                "discovered_at": datetime.now(timezone.utc),
            },
        )
        row = result.fetchone()
        return row[0] if row else discovery_id
    except Exception as exc:
        logger.debug("Discovery insert failed for %s: %s", url, exc)
        return None


def _article_exists(db: Session, url: str) -> bool:
    """Check if an article with this URL already exists."""
    try:
        row = db.execute(
            text("SELECT id FROM articles WHERE url = :url"), {"url": url}
        ).fetchone()
        return row is not None
    except Exception:
        return False


def _get_or_create_aggregator_source(db: Session, aggregator: str) -> Optional[str]:
    """Return source_id for the aggregator synthetic source, creating if needed."""
    domain_map = {
        "hn": "news.ycombinator.com",
        "lobsters": "lobste.rs",
        "pinboard": "pinboard.in",
        "reddit": "reddit.com",
    }
    domain = domain_map.get(aggregator)
    if not domain:
        return None

    try:
        row = db.execute(
            text("SELECT id FROM sources WHERE domain = :domain"), {"domain": domain}
        ).fetchone()
        if row:
            return row[0]

        source_id = str(uuid.uuid4())
        db.execute(
            text(
                """
                INSERT INTO sources
                    (id, domain, name, source_type, is_active, created_at)
                VALUES
                    (:id, :domain, :name, 'dynamic', 1, :created_at)
                ON CONFLICT (domain) DO NOTHING
                """
            ),
            {
                "id": source_id,
                "domain": domain,
                "name": aggregator.upper(),
                "created_at": datetime.now(timezone.utc),
            },
        )
        # Re-fetch in case ON CONFLICT fired
        row = db.execute(
            text("SELECT id FROM sources WHERE domain = :domain"), {"domain": domain}
        ).fetchone()
        return row[0] if row else source_id
    except Exception as exc:
        logger.debug("Failed to get/create source for %s: %s", aggregator, exc)
        return None


def _ingest_article(
    db: Session,
    url: str,
    title: Optional[str],
    aggregator: str,
    score: int,
    source_id: Optional[str],
) -> bool:
    """
    Full article ingestion: fetch content, apply hard gates, persist.
    Returns True if a new article was created.
    """
    if _article_exists(db, url):
        return False

    html_content, plain_text, word_count = _extract_content(url)

    passed, gate_reason = passes_hard_gates(
        url=url,
        word_count=word_count,
        html_content=html_content,
        db=db,
    )
    if not passed:
        logger.debug("Hard gate failed for %s: %s", url, gate_reason)
        return False

    # Normalise aggregator score to [0, 1] via log1p / 10
    import math
    agg_norm = min(1.0, math.log1p(score) / 10.0)

    quality = compute_quality_score(
        groq_quality_score=None,
        published_at=None,
        aggregator_score=float(score),
        source_type="dynamic",
    )

    article_title = (title or url[:200]).strip()[:500]

    article = Article(
        id=str(uuid.uuid4()),
        title=article_title,
        url=url,
        source=aggregator.upper(),
        author=None,
        summary=None,
        topics=[],
        read_time=max(1, word_count // 200) if word_count else None,
        source_type="Manual",
        status="Unread",
        curation_status="raw",
        published_at=None,
        word_count=word_count,
        source_id=source_id,
        groq_quality_score=None,
    )

    # Set aggregator_score if column exists
    try:
        article.aggregator_score = agg_norm
    except Exception:
        pass

    db.add(article)
    try:
        db.flush()
    except Exception as exc:
        logger.warning("DB flush failed for %s: %s", url, exc)
        db.rollback()
        return False

    enrich_article_embedding(article)
    return True


# ---------------------------------------------------------------------------
# Per-aggregator tap functions
# ---------------------------------------------------------------------------

def _tap_hn(db: Session, max_items: int) -> dict:
    """
    Tap HN Algolia search API for top stories.
    https://hn.algolia.com/api/v1/search?tags=story&hitsPerPage=50
    """
    stats = {"discoveries": 0, "new_articles": 0, "skipped": 0, "errors": 0}
    source_id = _get_or_create_aggregator_source(db, "hn")

    try:
        response = httpx.get(
            "https://hn.algolia.com/api/v1/search",
            params={"tags": "story", "hitsPerPage": min(max_items, 50)},
            timeout=FETCH_TIMEOUT,
            headers={"User-Agent": UA},
        )
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        logger.warning("HN Algolia fetch failed: %s", exc)
        stats["errors"] += 1
        return stats

    hits = data.get("hits", [])[:max_items]
    for hit in hits:
        url = hit.get("url") or hit.get("story_url")
        if not url:
            stats["skipped"] += 1
            continue

        title = hit.get("title")
        score = int(hit.get("points") or 0)
        comment_count = int(hit.get("num_comments") or 0)

        discovery_id = _persist_discovery(db, url, title, "hn", score, comment_count)
        if discovery_id:
            stats["discoveries"] += 1
        else:
            stats["errors"] += 1
            continue

        try:
            created = _ingest_article(db, url, title, "hn", score, source_id)
            if created:
                stats["new_articles"] += 1
            else:
                stats["skipped"] += 1
        except Exception as exc:
            logger.debug("HN article ingest failed for %s: %s", url, exc)
            stats["errors"] += 1

    return stats


def _tap_lobsters(db: Session, max_items: int) -> dict:
    """
    Tap Lobsters hottest stories JSON API.
    https://lobste.rs/hottest.json
    """
    stats = {"discoveries": 0, "new_articles": 0, "skipped": 0, "errors": 0}
    source_id = _get_or_create_aggregator_source(db, "lobsters")

    try:
        response = httpx.get(
            "https://lobste.rs/hottest.json",
            timeout=FETCH_TIMEOUT,
            headers={"User-Agent": UA},
        )
        response.raise_for_status()
        stories = response.json()
    except Exception as exc:
        logger.warning("Lobsters fetch failed: %s", exc)
        stats["errors"] += 1
        return stats

    for story in stories[:max_items]:
        url = story.get("url")
        if not url:
            stats["skipped"] += 1
            continue

        title = story.get("title")
        score = int(story.get("score") or 0)
        comment_count = int(story.get("comment_count") or 0)

        discovery_id = _persist_discovery(db, url, title, "lobsters", score, comment_count)
        if discovery_id:
            stats["discoveries"] += 1
        else:
            stats["errors"] += 1
            continue

        try:
            created = _ingest_article(db, url, title, "lobsters", score, source_id)
            if created:
                stats["new_articles"] += 1
            else:
                stats["skipped"] += 1
        except Exception as exc:
            logger.debug("Lobsters article ingest failed for %s: %s", url, exc)
            stats["errors"] += 1

    return stats


def _tap_pinboard(db: Session, max_items: int) -> dict:
    """
    Tap Pinboard popular RSS feed.
    https://feeds.pinboard.in/rss/popular/
    """
    stats = {"discoveries": 0, "new_articles": 0, "skipped": 0, "errors": 0}
    source_id = _get_or_create_aggregator_source(db, "pinboard")

    try:
        import feedparser
        feed = feedparser.parse(
            "https://feeds.pinboard.in/rss/popular/",
            agent=UA,
        )
        entries = feed.entries[:max_items]
    except Exception as exc:
        logger.warning("Pinboard RSS fetch failed: %s", exc)
        stats["errors"] += 1
        return stats

    for entry in entries:
        url = getattr(entry, "link", None)
        if not url:
            stats["skipped"] += 1
            continue

        title = getattr(entry, "title", None)
        # Pinboard doesn't expose explicit scores in RSS; use 1 as default
        score = 1
        comment_count = 0

        discovery_id = _persist_discovery(db, url, title, "pinboard", score, comment_count)
        if discovery_id:
            stats["discoveries"] += 1
        else:
            stats["errors"] += 1
            continue

        try:
            created = _ingest_article(db, url, title, "pinboard", score, source_id)
            if created:
                stats["new_articles"] += 1
            else:
                stats["skipped"] += 1
        except Exception as exc:
            logger.debug("Pinboard article ingest failed for %s: %s", url, exc)
            stats["errors"] += 1

    return stats


def _tap_reddit(db: Session, max_items: int) -> dict:
    """
    Tap Reddit JSON API for top posts across configured subreddits.
    """
    stats = {"discoveries": 0, "new_articles": 0, "skipped": 0, "errors": 0}
    source_id = _get_or_create_aggregator_source(db, "reddit")

    per_sub = max(1, max_items // len(REDDIT_SUBREDDITS))

    for subreddit in REDDIT_SUBREDDITS:
        try:
            response = httpx.get(
                f"https://www.reddit.com/r/{subreddit}/hot.json",
                params={"limit": per_sub},
                timeout=FETCH_TIMEOUT,
                headers={"User-Agent": UA},
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            logger.warning("Reddit /r/%s fetch failed: %s", subreddit, exc)
            stats["errors"] += 1
            continue

        posts = data.get("data", {}).get("children", [])
        for post_wrapper in posts:
            post = post_wrapper.get("data", {})
            url = post.get("url")

            # Skip Reddit self-posts, images, and videos
            if not url:
                stats["skipped"] += 1
                continue
            domain = _domain_from_url(url) or ""
            if domain in ("reddit.com", "i.redd.it", "v.redd.it", "redd.it"):
                stats["skipped"] += 1
                continue

            title = post.get("title")
            score = int(post.get("score") or 0)
            comment_count = int(post.get("num_comments") or 0)

            discovery_id = _persist_discovery(
                db, url, title, "reddit", score, comment_count
            )
            if discovery_id:
                stats["discoveries"] += 1
            else:
                stats["errors"] += 1
                continue

            try:
                created = _ingest_article(db, url, title, "reddit", score, source_id)
                if created:
                    stats["new_articles"] += 1
                else:
                    stats["skipped"] += 1
            except Exception as exc:
                logger.debug("Reddit article ingest failed for %s: %s", url, exc)
                stats["errors"] += 1

    return stats


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

TAP_REGISTRY = {
    "hn": _tap_hn,
    "lobsters": _tap_lobsters,
    "pinboard": _tap_pinboard,
    "reddit": _tap_reddit,
}


def tap_aggregators(
    db: Session,
    sources: Optional[list[str]] = None,
    max_per_source: int = MAX_DISCOVERIES_PER_SOURCE,
) -> dict:
    """
    Tap all (or a subset of) aggregator sources.

    sources: list of aggregator names to tap; None = all.
    max_per_source: max discoveries to process per aggregator.

    Returns aggregate stats dict.
    """
    if sources is None:
        sources = list(TAP_REGISTRY.keys())

    total_stats = {
        "sources_tapped": 0,
        "discoveries_found": 0,
        "new_articles": 0,
        "skipped": 0,
        "errors": 0,
        "per_source": {},
    }

    for name in sources:
        tap_fn = TAP_REGISTRY.get(name)
        if not tap_fn:
            logger.warning("Unknown aggregator: %s", name)
            continue

        logger.info("Tapping aggregator: %s", name)
        try:
            s = tap_fn(db, max_per_source)
        except Exception as exc:
            logger.error("Aggregator tap failed for %s: %s", name, exc)
            s = {"discoveries": 0, "new_articles": 0, "skipped": 0, "errors": 1}

        total_stats["sources_tapped"] += 1
        total_stats["discoveries_found"] += s.get("discoveries", 0)
        total_stats["new_articles"] += s.get("new_articles", 0)
        total_stats["skipped"] += s.get("skipped", 0)
        total_stats["errors"] += s.get("errors", 0)
        total_stats["per_source"][name] = s

        try:
            db.commit()
        except Exception as exc:
            logger.warning("Commit failed after %s tap: %s", name, exc)
            db.rollback()
            total_stats["errors"] += 1

    logger.info(
        "Aggregator tap complete: %d sources, %d discoveries, %d new articles",
        total_stats["sources_tapped"],
        total_stats["discoveries_found"],
        total_stats["new_articles"],
    )
    return total_stats
