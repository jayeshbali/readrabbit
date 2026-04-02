"""
Tests for quality_pipeline_service.py

Scenarios:
  1. Word count fail — low word count yields score below MIN_QUALITY_SCORE
  2. Good structure passes — high structure_score + static source_tier passes threshold
  3. Blacklisted domain fails — evaluate_article_quality returns None for blacklisted domain
"""

import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from quality_pipeline_service import (
    MIN_QUALITY_SCORE,
    compute_quality_score,
    evaluate_article_quality,
)


# ---------------------------------------------------------------------------
# compute_quality_score — pure math, no DB
# ---------------------------------------------------------------------------


def test_word_count_fail():
    """Very low word count + zero structure + probation tier → score below threshold."""
    # structure_score=0.0, source_type='probation' (tier=0.4), word_count=0
    # score = 0.4*0.0 + 0.4*0.4 + 0.2*min(1.0, 0/5000)
    #       = 0.0 + 0.16 + 0.0
    #       = 0.16
    score = compute_quality_score(structure_score=0.0, source_type="probation", word_count=0)
    assert score < MIN_QUALITY_SCORE, (
        f"Expected score {score:.3f} to be below MIN_QUALITY_SCORE ({MIN_QUALITY_SCORE})"
    )


def test_good_structure_passes():
    """Good structure + static source + sufficient word count → score above threshold."""
    # structure_score=0.9, source_type='static' (tier=1.0), word_count=5000
    # score = 0.4*0.9 + 0.4*1.0 + 0.2*min(1.0, 5000/5000)
    #       = 0.36 + 0.40 + 0.20
    #       = 0.96
    score = compute_quality_score(structure_score=0.9, source_type="static", word_count=5000)
    assert score >= MIN_QUALITY_SCORE, (
        f"Expected score {score:.3f} to be at or above MIN_QUALITY_SCORE ({MIN_QUALITY_SCORE})"
    )
    assert abs(score - 0.96) < 1e-9, f"Expected 0.96, got {score}"


# ---------------------------------------------------------------------------
# evaluate_article_quality — exercises the DB blacklist path
# ---------------------------------------------------------------------------


def _make_db(blacklisted: bool) -> MagicMock:
    """Return a mock SQLAlchemy Session whose blacklist query matches `blacklisted`."""
    db = MagicMock()
    row = MagicMock() if blacklisted else None
    db.execute.return_value.fetchone.return_value = row
    return db


def test_blacklisted_domain_fails():
    """evaluate_article_quality returns None when domain is in domain_blacklist."""
    db = _make_db(blacklisted=True)
    result = evaluate_article_quality(
        db=db,
        domain="spam.example.com",
        structure_score=0.9,
        source_type="static",
        word_count=5000,
    )
    assert result is None, "Expected None for a blacklisted domain"


def test_non_blacklisted_domain_passes():
    """evaluate_article_quality returns a float when domain is not blacklisted."""
    db = _make_db(blacklisted=False)
    result = evaluate_article_quality(
        db=db,
        domain="trusted.example.com",
        structure_score=0.9,
        source_type="static",
        word_count=5000,
    )
    assert result is not None, "Expected a float score for a non-blacklisted domain"
    assert isinstance(result, float)
    assert result >= MIN_QUALITY_SCORE
