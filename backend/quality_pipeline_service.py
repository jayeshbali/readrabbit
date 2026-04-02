"""
quality_pipeline_service.py — Article quality scoring for ingestion pipeline.

Formula:
  quality_score = 0.4 * structure_score + 0.4 * source_tier + 0.2 * min(1.0, word_count / 5000)

structure_score:  0.0–1.0, caller-supplied (based on title presence, content length, etc.)
source_tier:      1.0 for 'static', 0.7 for 'dynamic', 0.4 for 'probation'
word_count:       raw word count of article content

Returns None (article rejected) if:
  - The article's domain is in the domain_blacklist table
  - The computed quality_score is below MIN_QUALITY_SCORE

Returns the float quality_score on success.
"""

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Minimum score to pass ingestion
MIN_QUALITY_SCORE = 0.3

# Source tier weights
SOURCE_TIER_WEIGHTS: dict[str, float] = {
    "static": 1.0,
    "dynamic": 0.7,
    "probation": 0.4,
}

# Word count normaliser denominator
WORD_COUNT_NORM = 5000.0


def _is_blacklisted(db: Session, domain: str) -> bool:
    """Return True if domain appears in the domain_blacklist table."""
    try:
        row = db.execute(
            text("SELECT 1 FROM domain_blacklist WHERE domain = :domain LIMIT 1"),
            {"domain": domain},
        ).fetchone()
        return row is not None
    except Exception as exc:
        logger.warning("Blacklist check failed for %s: %s", domain, exc)
        return False


def compute_quality_score(
    structure_score: float,
    source_type: str,
    word_count: int,
) -> float:
    """
    Compute the quality score without any database interaction.

    structure_score: 0.0–1.0
    source_type:     'static' | 'dynamic' | 'probation'
    word_count:      raw word count

    Returns a float in [0.0, 1.0].
    """
    tier = SOURCE_TIER_WEIGHTS.get(source_type, 0.4)
    length_component = min(1.0, word_count / WORD_COUNT_NORM)
    return 0.4 * structure_score + 0.4 * tier + 0.2 * length_component


def evaluate_article_quality(
    db: Session,
    domain: str,
    structure_score: float,
    source_type: str,
    word_count: int,
) -> Optional[float]:
    """
    Full quality evaluation for a candidate article.

    Returns the quality score (float) if the article passes all checks,
    or None if it is rejected (blacklisted domain or score below threshold).

    Args:
        db:              SQLAlchemy session.
        domain:          Domain of the article's source (e.g. 'example.com').
        structure_score: Content structure quality, 0.0–1.0.
        source_type:     One of 'static', 'dynamic', 'probation'.
        word_count:      Number of words in the article body.
    """
    if _is_blacklisted(db, domain):
        logger.debug("Article rejected — domain blacklisted: %s", domain)
        return None

    score = compute_quality_score(structure_score, source_type, word_count)

    if score < MIN_QUALITY_SCORE:
        logger.debug(
            "Article rejected — quality score %.3f below threshold %.3f (domain=%s)",
            score,
            MIN_QUALITY_SCORE,
            domain,
        )
        return None

    logger.debug("Article accepted — quality score %.3f (domain=%s)", score, domain)
    return score
