"""
link_graph.py — Layer 2: Outbound link extraction and domain discovery.

For each recently-ingested article (curation_status='raw', html_content available):
  1. Parse outbound links from stored html_content via BeautifulSoup
  2. Skip internal links, blacklisted domains, already-known sources
  3. Persist citations to link_citations table
  4. Promote novel external domains as probation sources (is_active=0)

Returns a stats dict: {articles_scanned, citations_found, new_sources, skipped, errors}
"""

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urljoin, urlparse

from sqlalchemy import text
from sqlalchemy.orm import Session

from database import Article, Source

logger = logging.getLogger(__name__)

# Max articles to process per run (avoid runaway on large backlogs)
MAX_ARTICLES_PER_RUN = 200
# Max outbound links to record per article
MAX_LINKS_PER_ARTICLE = 50
# Minimum path depth to treat a link as a real article (not homepage/nav)
MIN_PATH_DEPTH = 1


def _domain_from_url(url: str) -> Optional[str]:
    """Extract bare domain (e.g. 'arstechnica.com') from a URL. Returns None on parse error."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return None
        host = parsed.netloc.lower()
        if not host:
            return None
        # Strip port if present
        host = host.split(":")[0]
        # Strip www. prefix
        if host.startswith("www."):
            host = host[4:]
        return host if host else None
    except Exception:
        return None


def _is_article_like(url: str) -> bool:
    """
    Heuristic: is this URL likely a real article rather than a nav/homepage link?
    Requires at least one path segment beyond the root.
    """
    try:
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        segments = [s for s in path.split("/") if s]
        return len(segments) >= MIN_PATH_DEPTH
    except Exception:
        return False


def _extract_links(html: str, base_url: str) -> list[dict]:
    """
    Extract outbound links from HTML content.
    Returns list of dicts: {url, domain, anchor_text}.

    Uses regex to avoid a BeautifulSoup dependency; covers standard <a href="..."> tags.
    """
    base_domain = _domain_from_url(base_url) or ""
    links = []
    seen_urls: set[str] = set()

    pattern = re.compile(
        r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )

    for m in pattern.finditer(html):
        raw_href = m.group(1).strip()
        anchor_raw = m.group(2)
        # Strip HTML tags from anchor text
        anchor_text = re.sub(r"<[^>]+>", " ", anchor_raw).strip()[:500] or None

        # Resolve relative URLs against base
        try:
            url = urljoin(base_url, raw_href)
        except Exception:
            continue

        if url in seen_urls:
            continue
        seen_urls.add(url)

        domain = _domain_from_url(url)
        if not domain:
            continue

        # Skip self-links
        if domain == base_domain:
            continue

        # Skip non-article-like URLs
        if not _is_article_like(url):
            continue

        links.append({"url": url, "domain": domain, "anchor_text": anchor_text})

        if len(links) >= MAX_LINKS_PER_ARTICLE:
            break

    return links


def _load_blacklist(db: Session) -> set[str]:
    """Load domain blacklist from DB."""
    try:
        rows = db.execute(text("SELECT domain FROM domain_blacklist")).fetchall()
        return {r[0] for r in rows}
    except Exception:
        return set()


def _known_domains(db: Session) -> set[str]:
    """Load all domains already in the sources table."""
    try:
        rows = db.execute(text("SELECT domain FROM sources")).fetchall()
        return {r[0] for r in rows}
    except Exception:
        return set()


def _persist_citation(
    db: Session,
    article: Article,
    cited_url: str,
    cited_domain: str,
    anchor_text: Optional[str],
) -> bool:
    """Insert a single link_citation row. Returns True on success."""
    try:
        db.execute(
            text(
                """
                INSERT INTO link_citations
                    (id, source_article_id, cited_domain, cited_url, anchor_text, created_at)
                VALUES
                    (:id, :source_article_id, :cited_domain, :cited_url, :anchor_text, :created_at)
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "source_article_id": article.id,
                "cited_domain": cited_domain,
                "cited_url": cited_url,
                "anchor_text": anchor_text,
                "created_at": datetime.now(timezone.utc),
            },
        )
        return True
    except Exception as exc:
        logger.debug("Citation insert failed for %s: %s", cited_url, exc)
        return False


def _promote_to_probation(
    db: Session,
    domain: str,
    discovered_via: Optional[str],
) -> bool:
    """
    Insert domain as a probation source (is_active=0, source_type='probation').
    Returns True if a new row was inserted, False if domain already exists.
    """
    try:
        result = db.execute(
            text(
                """
                INSERT INTO sources
                    (id, domain, name, source_type, is_active, created_at, discovered_via, probation_start)
                VALUES
                    (:id, :domain, :name, 'probation', 0, :created_at, :discovered_via, :probation_start)
                ON CONFLICT (domain) DO NOTHING
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "domain": domain,
                "name": domain,  # placeholder name — can be enriched later
                "created_at": datetime.now(timezone.utc),
                "discovered_via": discovered_via,
                "probation_start": datetime.now(timezone.utc),
            },
        )
        return result.rowcount > 0
    except Exception as exc:
        logger.debug("Probation insert failed for %s: %s", domain, exc)
        return False


def process_article_links(article: Article, db: Session) -> dict:
    """
    Process outbound links for a single article.
    Returns per-article stats: {citations_found, new_sources, skipped, errors}.
    """
    stats = {"citations_found": 0, "new_sources": 0, "skipped": 0, "errors": 0}

    # We need the HTML content — stored on the article? No, feed_crawler doesn't
    # persist html to the articles table. We re-fetch if needed, but to keep this
    # layer lightweight we use the article URL as base and rely on the crawled HTML
    # being available via a companion column, OR we skip articles without HTML.
    # Since feed_crawler.py doesn't store html_content on the Article ORM object
    # (only word_count and plain text quality signals), we skip articles lacking
    # sufficient word_count as a proxy for "we couldn't fetch content anyway".
    if not article.url:
        stats["skipped"] += 1
        return stats

    # Fetch the article's HTML content fresh for link extraction
    # (lightweight re-fetch — we only need links, not full text)
    try:
        import httpx

        UA = "ReadRabbit/1.0 (link-graph; +https://readrabbit.app)"
        response = httpx.get(
            article.url,
            follow_redirects=True,
            timeout=10,
            headers={"User-Agent": UA},
        )
        response.raise_for_status()
        html = response.text
    except Exception as exc:
        logger.debug("Failed to fetch HTML for link extraction %s: %s", article.url, exc)
        stats["errors"] += 1
        return stats

    if not html:
        stats["skipped"] += 1
        return stats

    links = _extract_links(html, article.url)
    if not links:
        return stats

    blacklist = _load_blacklist(db)
    known = _known_domains(db)

    new_domains_this_article: set[str] = set()

    for link in links:
        domain = link["domain"]
        url = link["url"]
        anchor = link["anchor_text"]

        # Skip blacklisted domains
        if domain in blacklist:
            stats["skipped"] += 1
            continue

        # Persist citation regardless of whether source is new
        ok = _persist_citation(db, article, url, domain, anchor)
        if ok:
            stats["citations_found"] += 1
        else:
            stats["errors"] += 1
            continue

        # Promote new domains to probation (once per domain per run)
        if domain not in known and domain not in new_domains_this_article:
            promoted = _promote_to_probation(db, domain, article.url)
            if promoted:
                stats["new_sources"] += 1
                new_domains_this_article.add(domain)
                known.add(domain)  # prevent duplicate promotion within this article

    return stats


def expand_link_graph(db: Session, max_articles: int = MAX_ARTICLES_PER_RUN) -> dict:
    """
    Process outbound links for recently-ingested articles.

    Targets articles with curation_status='raw' that have not been link-scanned yet,
    using the presence of link_citations rows as a processed marker.

    Returns aggregate stats dict.
    """
    # Articles to scan: raw status, not yet link-scanned
    # We use a LEFT JOIN to exclude articles already in link_citations as source
    try:
        rows = db.execute(
            text(
                """
                SELECT a.id, a.url, a.source_id
                FROM articles a
                LEFT JOIN link_citations lc ON lc.source_article_id = a.id
                WHERE a.curation_status = 'raw'
                  AND a.url IS NOT NULL
                  AND a.word_count >= 500
                  AND lc.id IS NULL
                ORDER BY a.created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": max_articles},
        ).fetchall()
    except Exception as exc:
        logger.error("Failed to query articles for link graph: %s", exc)
        return {
            "articles_scanned": 0,
            "citations_found": 0,
            "new_sources": 0,
            "skipped": 0,
            "errors": 1,
        }

    total_stats = {
        "articles_scanned": 0,
        "citations_found": 0,
        "new_sources": 0,
        "skipped": 0,
        "errors": 0,
    }

    for row in rows:
        article_id, url, source_id = row[0], row[1], row[2]

        # Build a minimal Article-like object for citation insertion
        article = Article.__new__(Article)
        article.id = article_id
        article.url = url
        article.source_id = source_id

        logger.debug("Link-scanning article: %s", url)
        s = process_article_links(article, db)
        total_stats["articles_scanned"] += 1
        total_stats["citations_found"] += s.get("citations_found", 0)
        total_stats["new_sources"] += s.get("new_sources", 0)
        total_stats["skipped"] += s.get("skipped", 0)
        total_stats["errors"] += s.get("errors", 0)

        # Commit per article to avoid holding a giant transaction
        try:
            db.commit()
        except Exception as exc:
            logger.warning("Commit failed after link-scan for %s: %s", url, exc)
            db.rollback()
            total_stats["errors"] += 1

    logger.info(
        "Link graph expansion complete: %d articles scanned, %d citations, %d new probation sources",
        total_stats["articles_scanned"],
        total_stats["citations_found"],
        total_stats["new_sources"],
    )
    return total_stats
