"""
simple_feed_crawler.py — Dead-simple sequential RSS feed crawler.

No async concurrency, no semaphores, no rate limiting.
Just a sequential loop: parse feed → check entries → fetch URL → extract text → store.

Returns: dict with keys new, skipped, errors, sources_crawled
"""

import logging
import uuid
from datetime import datetime, timezone

import feedparser
import httpx
import trafilatura
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import Article, Source

logger = logging.getLogger(__name__)

MIN_WORD_COUNT = 1500
MAX_ENTRIES_PER_SOURCE = 10
FETCH_TIMEOUT = 15
UA = "ReadRabbit/1.0 (simple feed crawler)"


async def crawl_all_feeds(db: Session) -> dict:
    """
    Sequentially crawl all active sources with a feed_url.
    Uses synchronous feedparser, httpx, and trafilatura inside an async wrapper.
    """
    stats = {"new": 0, "skipped": 0, "errors": 0, "sources_crawled": 0}

    # Get all active sources with a feed URL
    sources = (
        db.query(Source)
        .filter(Source.is_active == 1, Source.feed_url.isnot(None))
        .all()
    )

    for source in sources:
        stats["sources_crawled"] += 1
        try:
            _crawl_source(source, db, stats)
        except Exception as exc:
            logger.warning("Unexpected error crawling %s: %s", source.domain, exc)
            stats["errors"] += 1

    try:
        db.commit()
    except Exception as exc:
        logger.error("Final commit failed: %s", exc)
        db.rollback()

    logger.info(
        "Simple crawl complete: %d sources, %d new, %d skipped, %d errors",
        stats["sources_crawled"],
        stats["new"],
        stats["skipped"],
        stats["errors"],
    )
    return stats


def _crawl_source(source: Source, db: Session, stats: dict) -> None:
    """Crawl a single source synchronously."""
    # Parse the feed
    try:
        feed = feedparser.parse(
            source.feed_url,
            agent=UA,
            request_headers={"Accept-Encoding": "gzip, deflate"},
        )
    except Exception as exc:
        logger.warning("feedparser error for %s: %s", source.domain, exc)
        stats["errors"] += 1
        return

    entries = (feed.entries or [])[:MAX_ENTRIES_PER_SOURCE]

    for entry in entries:
        url = getattr(entry, "link", None)
        if not url:
            stats["skipped"] += 1
            continue
        url = url.strip()

        # Dedup check
        existing = db.execute(
            text("SELECT id FROM articles WHERE url = :url"), {"url": url}
        ).fetchone()
        if existing:
            stats["skipped"] += 1
            continue

        # Fetch article HTML
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
            stats["errors"] += 1
            continue

        # Extract plain text
        try:
            plain_text = trafilatura.extract(
                raw_html,
                include_comments=False,
                include_tables=False,
                no_fallback=False,
            )
        except Exception as exc:
            logger.debug("trafilatura failed for %s: %s", url, exc)
            plain_text = None

        if not plain_text:
            stats["skipped"] += 1
            continue

        word_count = len(plain_text.split())
        if word_count < MIN_WORD_COUNT:
            stats["skipped"] += 1
            continue

        # Build Article record
        title = (getattr(entry, "title", None) or url[:200]).strip()[:500]
        read_time = round(word_count / 238, 1)

        author = getattr(entry, "author", None)
        ss = 0
        if title and len(title) > 10: ss += 0.2
        if author: ss += 0.2
        paragraphs = [p for p in plain_text.split('\n\n') if len(p.split()) > 50]
        if len(paragraphs) >= 3: ss += 0.2
        if word_count > 2500: ss += 0.2
        quality_score = 0.4 * ss + 0.4 * 1.0 + 0.2 * min(1.0, word_count / 5000)

        article = Article(
            id=str(uuid.uuid4()),
            title=title,
            url=url,
            source=source.name,
            source_id=source.id,
            word_count=word_count,
            read_time=int(read_time),
            groq_quality_score=quality_score,
            curation_status="raw",
            status="Unread",
            topics=[],
            published_at=None,
        )

        db.add(article)
        try:
            db.flush()
            stats["new"] += 1
        except Exception as exc:
            logger.warning("DB flush failed for %s: %s", url, exc)
            db.rollback()
            stats["errors"] += 1
