"""
Tests for feed_crawler.py

Scenarios:
  1. Mock RSS feed — feedparser returns one entry, article is inserted with status 'new'
  2. Dedup — same URL processed twice, second call returns status 'skipped'
  3. Feed timeout — feedparser exception on one source does not stop other sources
"""

import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from feed_crawler import crawl_all_sources, fetch_and_process_article


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source(domain="example.com", feed_url="https://example.com/feed.xml"):
    source = MagicMock()
    source.id = "src-1"
    source.name = "Example Blog"
    source.domain = domain
    source.feed_url = feed_url
    source.source_type = "static"
    source.is_active = 1
    source.poll_interval_hrs = 24
    return source


def _make_entry(url="https://example.com/article-1", title="Test Article"):
    entry = SimpleNamespace(
        link=url,
        title=title,
        author="Author Name",
        summary="This is a short summary of the test article.",
        published_parsed=None,
        updated_parsed=None,
        created_parsed=None,
    )
    return entry


def _make_db(url_exists=False):
    """Return a mock SQLAlchemy Session."""
    db = MagicMock()
    # execute().fetchone() — used for dedup check and blacklist check
    row = MagicMock() if url_exists else None
    db.execute.return_value.fetchone.return_value = row
    db.flush = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()
    return db


# ---------------------------------------------------------------------------
# Test 1: Mock RSS feed — article inserted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_new_article_inserted():
    """feedparser returns one entry; article is fetched and inserted with status 'new'."""
    db = _make_db(url_exists=False)
    source = _make_source()
    entry = _make_entry()

    domain_semaphores = {}

    with (
        patch(
            "feed_crawler._extract_content",
            new=AsyncMock(
                return_value=("<html>body</html>", "Long article body " * 30, 300)
            ),
        ),
        patch(
            "feed_crawler.evaluate_article_quality",
            return_value=0.85,
        ),
        patch(
            "feed_crawler.ai_service.generate_article_embedding",
            new=AsyncMock(return_value=[0.1] * 384),
        ),
    ):
        result = await fetch_and_process_article(
            url=entry.link,
            source=source,
            entry=entry,
            db=db,
            domain_semaphores=domain_semaphores,
        )

    assert result is not None
    assert result["status"] == "new"
    assert result["url"] == entry.link
    assert result["quality_score"] == pytest.approx(0.85)
    db.add.assert_called_once()
    db.flush.assert_called()


# ---------------------------------------------------------------------------
# Test 2: Dedup — same URL submitted twice
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_url_skipped():
    """Calling fetch_and_process_article twice for the same URL: second call returns 'skipped'."""
    source = _make_source()
    entry = _make_entry()
    domain_semaphores = {}

    # First call: URL does not exist in DB
    db_first = _make_db(url_exists=False)

    with (
        patch(
            "feed_crawler._extract_content",
            new=AsyncMock(
                return_value=("<html>body</html>", "Long article body " * 30, 300)
            ),
        ),
        patch("feed_crawler.evaluate_article_quality", return_value=0.85),
        patch(
            "feed_crawler.ai_service.generate_article_embedding",
            new=AsyncMock(return_value=None),
        ),
    ):
        first_result = await fetch_and_process_article(
            url=entry.link,
            source=source,
            entry=entry,
            db=db_first,
            domain_semaphores=domain_semaphores,
        )

    assert first_result["status"] == "new"

    # Second call: URL now exists in DB (dedup)
    db_second = _make_db(url_exists=True)

    second_result = await fetch_and_process_article(
        url=entry.link,
        source=source,
        entry=entry,
        db=db_second,
        domain_semaphores=domain_semaphores,
    )

    assert second_result is not None
    assert second_result["status"] == "skipped"
    assert second_result["quality_score"] is None
    db_second.add.assert_not_called()


# ---------------------------------------------------------------------------
# Test 3: Feed timeout — one source exception does not stop the pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feed_exception_does_not_stop_other_sources():
    """
    When feedparser raises an exception for one source, crawl_all_sources continues
    and still processes the remaining sources.
    """
    failing_source = _make_source(
        domain="failing.com", feed_url="https://failing.com/feed.xml"
    )
    failing_source.id = "src-fail"

    ok_source = _make_source(
        domain="ok.com", feed_url="https://ok.com/feed.xml"
    )
    ok_source.id = "src-ok"

    ok_entry = _make_entry(url="https://ok.com/article-1", title="Good Article")

    def _feedparser_side_effect(url, **kwargs):
        if "failing" in url:
            raise OSError("connection timed out")
        feed = SimpleNamespace(entries=[ok_entry])
        return feed

    db = _make_db(url_exists=False)
    db.query.return_value.filter.return_value.all.return_value = [
        failing_source,
        ok_source,
    ]

    with (
        patch(
            "feed_crawler.asyncio.to_thread",
            new=AsyncMock(side_effect=_feedparser_side_effect),
        ),
        patch(
            "feed_crawler._extract_content",
            new=AsyncMock(
                return_value=("<html>body</html>", "Long article body " * 30, 300)
            ),
        ),
        patch("feed_crawler.evaluate_article_quality", return_value=0.75),
        patch(
            "feed_crawler.ai_service.generate_article_embedding",
            new=AsyncMock(return_value=None),
        ),
    ):
        stats = await crawl_all_sources(db, force=True)

    # Two sources attempted; the failing one counted as an error, the OK one succeeded
    assert stats["sources_crawled"] == 2
    assert stats["errors"] >= 1
    assert stats["new_articles"] >= 1
