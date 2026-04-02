"""
quality_pipeline.py — Hard gates + scored signals for article quality.

Hard gates (any failure = reject):
  - word_count >= 1500
  - link_density < 0.15  (links / words)
  - domain not in domain_blacklist

Scored signals (0.0–1.0 composite):
  - groq_quality_score  (0.4 weight) — LLM-assessed quality
  - freshness           (0.3 weight) — exponential decay by age
  - aggregator_boost    (0.2 weight) — HN/Lobsters/Reddit score signal
  - source_tier         (0.1 weight) — static=1.0, dynamic=0.9, probation=0.7

Embeddings generated via generate_article_embedding() from ai_service.py.
"""

import math
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

try:
    from ai_service import generate_article_embedding
except Exception:
    generate_article_embedding = None  # type: ignore

BLACKLIST_CACHE: set[str] = set()
BLACKLIST_LOADED = False


def _load_blacklist(db: Session) -> set[str]:
    global BLACKLIST_CACHE, BLACKLIST_LOADED
    if BLACKLIST_LOADED:
        return BLACKLIST_CACHE
    try:
        from sqlalchemy import text
        rows = db.execute(text("SELECT domain FROM domain_blacklist")).fetchall()
        BLACKLIST_CACHE = {r[0] for r in rows}
    except Exception:
        BLACKLIST_CACHE = set()
    BLACKLIST_LOADED = True
    return BLACKLIST_CACHE


def _domain_from_url(url: str) -> str:
    """Extract bare domain (e.g. 'arstechnica.com') from a URL."""
    url = re.sub(r"^https?://", "", url)
    url = url.split("/")[0]
    return url.lower().lstrip("www.")


def _count_words(text: str) -> int:
    return len(text.split()) if text else 0


def _link_density(html: str) -> float:
    """Approximate link density: anchor text words / total words."""
    if not html:
        return 0.0
    anchor_words = sum(
        len(m.split())
        for m in re.findall(r"<a[^>]*>(.*?)</a>", html, re.IGNORECASE | re.DOTALL)
    )
    total_words = _count_words(re.sub(r"<[^>]+>", " ", html))
    if total_words == 0:
        return 0.0
    return anchor_words / total_words


def passes_hard_gates(
    url: str,
    word_count: int,
    html_content: Optional[str],
    db: Session,
) -> tuple[bool, str]:
    """
    Returns (passes: bool, reason: str).
    reason is empty string on pass, failure description on reject.
    """
    blacklist = _load_blacklist(db)
    domain = _domain_from_url(url)
    if domain in blacklist:
        return False, f"domain blacklisted: {domain}"

    if word_count < 1500:
        return False, f"too short: {word_count} words (min 1500)"

    if html_content:
        density = _link_density(html_content)
        if density >= 0.15:
            return False, f"link density too high: {density:.2f} (max 0.15)"

    return True, ""


def _freshness_score(published_at: Optional[datetime]) -> float:
    """Exponential decay: score = exp(-0.05 * days_old), floors at 0.1."""
    if published_at is None:
        return 0.5
    now = datetime.now(timezone.utc)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    days = max(0.0, (now - published_at).total_seconds() / 86400)
    return max(0.1, math.exp(-0.05 * days))


def _source_tier_score(source_type: Optional[str]) -> float:
    mapping = {"static": 1.0, "dynamic": 0.9, "probation": 0.7}
    return mapping.get(source_type or "static", 1.0)


def compute_quality_score(
    groq_quality_score: Optional[float],
    published_at: Optional[datetime],
    aggregator_score: float = 0.0,
    source_type: Optional[str] = "static",
) -> float:
    """
    Composite quality score in [0, 1].

    Weights:
      groq_quality_score : 0.4
      freshness          : 0.3
      aggregator_boost   : 0.2  (normalised to [0,1] via log1p / 10)
      source_tier        : 0.1
    """
    groq = groq_quality_score if groq_quality_score is not None else 0.5
    freshness = _freshness_score(published_at)
    agg_norm = min(1.0, math.log1p(aggregator_score) / 10.0)
    tier = _source_tier_score(source_type)

    return 0.4 * groq + 0.3 * freshness + 0.2 * agg_norm + 0.1 * tier


def enrich_article_embedding(article) -> bool:
    """
    Generates and attaches embedding to article ORM object in-place.
    Returns True if embedding was set, False otherwise.
    """
    if generate_article_embedding is None:
        return False
    if article.embedding is not None:
        return True  # already has one

    text_for_embedding = " ".join(filter(None, [
        article.title,
        article.summary,
    ]))
    if not text_for_embedding.strip():
        return False

    try:
        embedding = generate_article_embedding(text_for_embedding)
        if embedding:
            article.embedding = embedding
            return True
    except Exception:
        pass
    return False
