"""
feed_crawler.py — Layer 1: RSS/Atom feed crawl from sources table.

For each active source with a feed_url:
  1. Fetch feed via feedparser
  2. Extract full article content via trafilatura (readability-lxml fallback)
  3. Apply quality scoring from quality_pipeline_service.py
  4. Persist new articles to articles table (curation_status='raw')
  5. Update sources.last_crawled_at, article_count, avg_quality_score
  6. Generate embeddings via ai_service.generate_article_embedding()

Returns a stats dict: {sources_crawled, new_articles, skipped, errors}
"""

import asyncio
import logging
import re
import time as _time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

import feedparser
import httpx

try:
    import trafilatura
except ImportError:
    trafilatura = None  # type: ignore

try:
    from readability import Document as ReadabilityDoc
except ImportError:
    ReadabilityDoc = None  # type: ignore

from sqlalchemy import text
from sqlalchemy.orm import Session

import ai_service
from database import Article, Source
from quality_pipeline_service import evaluate_article_quality

logger = logging.getLogger(__name__)

# HTTP timeout for fetching article content
FETCH_TIMEOUT = 15
# Max articles to process per source per crawl run
MAX_ARTICLES_PER_SOURCE = 50
# User-agent string
UA = "ReadRabbit/1.0 (feed crawler; +https://readrabbit.app)"
# Max concurrent feed fetches across all sources
FEED_SEMAPHORE_LIMIT = 5
# Max concurrent article fetches per domain
DOMAIN_ARTICLE_SEMAPHORE_LIMIT = 3
# Delay between article fetches to the same domain (seconds)
DOMAIN_FETCH_DELAY = 1.0


# ---------------------------------------------------------------------------
# Helpers (sync — called from async context via to_thread or directly)
# ---------------------------------------------------------------------------


def _parse_published_at(entry) -> Optional[datetime]:
    """Extract published datetime from a feedparser entry."""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        t = getattr(entry, attr, None)
        if t is not None:
            try:
                return datetime.fromtimestamp(_time.mktime(t), tz=timezone.utc)
            except Exception:
                pass
    return None


def _entry_url(entry) -> Optional[str]:
    """Get canonical URL from a feedparser entry."""
    url = getattr(entry, "link", None)
    if url:
        return url.strip()
    return None


# ---------------------------------------------------------------------------
# Async content extraction
# ---------------------------------------------------------------------------


async def _extract_content(url: str) -> tuple[Optional[str], Optional[str], int]:
    """
    Fetch and extract full article text from a URL asynchronously.
    Returns (html_content, plain_text, word_count).
    Tries trafilatura first, falls back to readability-lxml.
    """
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=FETCH_TIMEOUT,
            max_redirects=3,
            headers={"User-Agent": UA},
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            raw_html = response.text
    except Exception as exc:
        logger.debug("Failed to fetch %s: %s", url, exc)
        return None, None, 0

    plain_text = None

    # Try trafilatura first (run in thread to avoid blocking event loop)
    if trafilatura is not None:
        try:
            plain_text = await asyncio.to_thread(
                trafilatura.extract,
                raw_html,
                include_comments=False,
                include_tables=False,
                no_fallback=False,
            )
        except Exception:
            pass

    # Fallback to readability-lxml
    if not plain_text and ReadabilityDoc is not None:
        try:
            doc = ReadabilityDoc(raw_html)
            summary_html = doc.summary()
            plain_text = re.sub(r"<[^>]+>", " ", summary_html)
        except Exception:
            pass

    if not plain_text:
        return raw_html, None, 0

    word_count = len(plain_text.split())
    return raw_html, plain_text, word_count


# ---------------------------------------------------------------------------
# Per-article async processing
# ---------------------------------------------------------------------------


async def fetch_and_process_article(
    url: str,
    source: Source,
    entry,
    db: Session,
    domain_semaphores: dict,
) -> Optional[dict]:
    """
    Fetch, score, embed, and insert a single article.

    Returns a result dict with keys: url, status ('new'|'skipped'|'error'),
    quality_score. Returns None on unexpected error.

    domain_semaphores: dict mapping domain str → asyncio.Semaphore(DOMAIN_ARTICLE_SEMAPHORE_LIMIT)
    """
    domain = source.domain

    # Ensure per-domain semaphore exists (caller pre-populates, but be safe)
    if domain not in domain_semaphores:
        domain_semaphores[domain] = asyncio.Semaphore(DOMAIN_ARTICLE_SEMAPHORE_LIMIT)

    async with domain_semaphores[domain]:
        # Rate-limit: pause between article fetches to the same domain
        await asyncio.sleep(DOMAIN_FETCH_DELAY)

        # Dedup check
        existing = db.execute(
            text("SELECT id FROM articles WHERE url = :url"), {"url": url}
        ).fetchone()
        if existing:
            return {"url": url, "status": "skipped", "quality_score": None}

        # Fetch full content
        _html, plain_text, word_count = await _extract_content(url)

        # Title
        title = (getattr(entry, "title", None) or url[:200]).strip()[:500]

        # Author
        author = None
        if hasattr(entry, "author"):
            author = str(entry.author).strip()[:200] or None

        # Summary (from feed)
        feed_summary = getattr(entry, "summary", None) or getattr(entry, "description", None)
        if feed_summary:
            feed_summary = re.sub(r"<[^>]+>", " ", feed_summary).strip()[:2000] or None

        published_at = _parse_published_at(entry)

        # Inline 5-criterion structure scoring
        structure_score = 0.0
        # Criterion 1: title exists and is substantial
        if title and len(title) > 10:
            structure_score += 0.2
        # Criterion 2: author/byline found in feed entry
        if author is not None:
            structure_score += 0.2
        # Criteria 3 & 4: paragraph and subheading checks require plain_text
        if plain_text:
            paragraphs = [p.strip() for p in plain_text.split("\n\n") if p.strip()]
            long_paragraphs = [p for p in paragraphs if len(p.split()) > 50]
            # Criterion 3: 3+ paragraphs over 50 words each
            if len(long_paragraphs) >= 3:
                structure_score += 0.2
            # Criterion 4: text has subheadings (short lines followed by longer paragraphs)
            lines = plain_text.split("\n")
            has_subheadings = False
            for i, line in enumerate(lines):
                if line.strip() and len(line.strip()) < 80:
                    # Look for a longer paragraph following this short line
                    for j in range(i + 1, min(i + 4, len(lines))):
                        if len(lines[j].split()) > 20:
                            has_subheadings = True
                            break
                if has_subheadings:
                    break
            if has_subheadings:
                structure_score += 0.2
        # Criterion 5: substantial word count
        if word_count > 2500:
            structure_score += 0.2

        # Source tier weighting
        source_type = source.source_type or "static"
        if source_type == "static":
            source_tier = 1.0
        elif source_type == "dynamic":
            source_tier = 0.9
        elif source_type == "probation":
            source_tier = 0.7
        else:
            source_tier = 1.0

        quality_score = (
            0.4 * structure_score
            + 0.4 * source_tier
            + 0.2 * min(1.0, word_count / 5000)
        )

        # Build Article ORM object
        article = Article(
            id=str(uuid.uuid4()),
            title=title,
            url=url,
            source=source.name,
            author=author,
            summary=feed_summary,
            topics=[],
            read_time=max(1, word_count // 200) if word_count else None,
            source_type="Manual",
            status="Unread",
            curation_status="raw",
            published_at=published_at,
            word_count=word_count,
            source_id=source.id,
            groq_quality_score=quality_score,
        )

        db.add(article)
        try:
            db.flush()
        except Exception as exc:
            logger.warning("DB flush failed for %s: %s", url, exc)
            db.rollback()
            return {"url": url, "status": "error", "quality_score": None}

        # Update avg_quality_score on the source record
        try:
            db.execute(
                text(
                    """UPDATE sources
                       SET avg_quality_score = (
                           COALESCE(avg_quality_score, 0) * COALESCE(article_count, 0) + :score
                       ) / (COALESCE(article_count, 0) + 1)
                       WHERE id = :source_id"""
                ),
                {"score": quality_score, "source_id": source.id},
            )
        except Exception as exc:
            logger.debug("avg_quality_score update failed for source %s: %s", source.id, exc)

        # Generate embedding (best-effort — don't fail article insert on embed error)
        try:
            embedding = await ai_service.generate_article_embedding(
                {
                    "title": title,
                    "summary": feed_summary or "",
                    "topics": [],
                    "source": source.name,
                    "author": author or "",
                }
            )
            if embedding and hasattr(article, "embedding"):
                article.embedding = embedding
                db.flush()
        except Exception as exc:
            logger.debug("Embedding generation failed for %s: %s", url, exc)

        return {"url": url, "status": "new", "quality_score": quality_score}


def _compute_structure_score(
    title: Optional[str],
    summary: Optional[str],
    word_count: int,
) -> float:
    """
    Heuristic structure score in [0.0, 1.0] based on available content signals.
    Used as input to quality_pipeline_service.compute_quality_score().
    """
    score = 0.0
    if title and len(title) > 10:
        score += 0.4
    if summary and len(summary) > 50:
        score += 0.3
    if word_count >= 300:
        score += 0.3
    elif word_count >= 100:
        score += 0.15
    return min(score, 1.0)


# ---------------------------------------------------------------------------
# Per-source async crawl
# ---------------------------------------------------------------------------


async def _crawl_source_async(
    source: Source,
    db: Session,
    feed_semaphore: asyncio.Semaphore,
    domain_semaphores: dict,
    max_articles: int = MAX_ARTICLES_PER_SOURCE,
) -> dict:
    """
    Async crawl of a single source feed. Acquires the global feed semaphore.
    Returns per-source stats dict.
    """
    stats = {"new": 0, "skipped": 0, "errors": 0, "source": source.domain, "quality_scores": []}

    if not source.feed_url:
        return stats

    async with feed_semaphore:
        try:
            feed = await asyncio.to_thread(
                feedparser.parse,
                source.feed_url,
                agent=UA,
                request_headers={"Accept-Encoding": "gzip, deflate"},
            )
        except Exception as exc:
            logger.warning("feedparser error for %s: %s", source.domain, exc)
            stats["errors"] += 1
            return stats

    entries = feed.entries[:max_articles]

    # Process articles concurrently (domain semaphore limits parallelism per domain)
    tasks = []
    for entry in entries:
        url = _entry_url(entry)
        if not url:
            stats["skipped"] += 1
            continue
        tasks.append(
            fetch_and_process_article(url, source, entry, db, domain_semaphores)
        )

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            logger.warning("Unexpected error processing article for %s: %s", source.domain, result)
            stats["errors"] += 1
        elif result is None:
            stats["errors"] += 1
        elif result["status"] == "new":
            stats["new"] += 1
            if result["quality_score"] is not None:
                stats["quality_scores"].append(result["quality_score"])
        elif result["status"] == "skipped":
            stats["skipped"] += 1
        else:
            stats["errors"] += 1

    # Commit all inserts for this source
    try:
        db.commit()
    except Exception as exc:
        logger.error("Commit failed for source %s: %s", source.domain, exc)
        db.rollback()
        stats["errors"] += stats["new"]
        stats["new"] = 0
        return stats

    # Update source metadata
    now = datetime.now(timezone.utc)
    quality_scores = stats.pop("quality_scores", [])
    avg_q = sum(quality_scores) / len(quality_scores) if quality_scores else None

    try:
        update_params: dict = {"last_crawled": now, "source_id": source.id, "new_count": stats["new"]}
        avg_clause = ""
        if avg_q is not None:
            update_params["avg_q"] = avg_q
            avg_clause = ", avg_quality_score = :avg_q"

        db.execute(
            text(
                f"""UPDATE sources
                   SET last_crawled_at = :last_crawled,
                       article_count = COALESCE(article_count, 0) + :new_count
                       {avg_clause}
                   WHERE id = :source_id"""
            ),
            update_params,
        )
        db.commit()
    except Exception as exc:
        logger.warning("Source metadata update failed for %s: %s", source.domain, exc)
        db.rollback()

    return stats


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


async def crawl_all_sources(
    db: Session,
    force: bool = False,
    max_sources: Optional[int] = None,
    max_articles: int = MAX_ARTICLES_PER_SOURCE,
) -> dict:
    """
    Crawl all active sources that have a feed_url and are due for polling.

    force=True ignores last_crawled_at / poll_interval_hrs and crawls all.
    max_sources limits how many sources are crawled in this run.
    max_articles limits how many feed entries are processed per source.

    Returns aggregate stats dict.
    """
    query = db.query(Source).filter(
        Source.is_active == 1,
        Source.feed_url.isnot(None),
    )

    if not force:
        query = query.filter(
            text(
                """(last_crawled_at IS NULL OR
                    last_crawled_at < NOW() - INTERVAL '1 hour' * COALESCE(poll_interval_hrs, 24))"""
            )
        )

    if max_sources is not None:
        query = query.limit(max_sources)

    sources = query.all()

    total_stats: dict = {
        "sources_crawled": 0,
        "new_articles": 0,
        "skipped": 0,
        "errors": 0,
        "per_source": [],
    }

    if not sources:
        return total_stats

    feed_semaphore = asyncio.Semaphore(FEED_SEMAPHORE_LIMIT)
    # Pre-populate one semaphore per unique domain
    domain_semaphores: dict = defaultdict(
        lambda: asyncio.Semaphore(DOMAIN_ARTICLE_SEMAPHORE_LIMIT)
    )

    source_tasks = [
        _crawl_source_async(source, db, feed_semaphore, domain_semaphores, max_articles)
        for source in sources
    ]

    source_results = await asyncio.gather(*source_tasks, return_exceptions=True)

    for result in source_results:
        if isinstance(result, Exception):
            logger.error("Unexpected error crawling source: %s", result)
            total_stats["errors"] += 1
            continue

        total_stats["sources_crawled"] += 1
        total_stats["new_articles"] += result.get("new", 0)
        total_stats["skipped"] += result.get("skipped", 0)
        total_stats["errors"] += result.get("errors", 0)
        total_stats["per_source"].append(result)

    logger.info(
        "Feed crawl complete: %d sources, %d new, %d skipped, %d errors",
        total_stats["sources_crawled"],
        total_stats["new_articles"],
        total_stats["skipped"],
        total_stats["errors"],
    )
    return total_stats
