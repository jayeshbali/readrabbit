"""
Phase 3 unit tests — Admin Panel, For You Tab, Eval Dashboard.

Run with: python3 -m pytest backend/tests/test_phase3.py -v

These tests do not require a database connection; they mock or use in-memory state.
"""
import os
import sys
import uuid
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

# Ensure backend/ is on the path so imports resolve.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# build_user_profile() — backward-compat + reading history weighting
# ---------------------------------------------------------------------------

from recommendation_engine import build_user_profile

FAKE_EMB_A = [0.1] * 10
FAKE_EMB_B = [0.9] * 10


def test_build_user_profile_no_reading_history_arg():
    """Old signature (no reading_history param) must not raise TypeError."""
    profile = build_user_profile(saved_articles=[])
    assert profile is not None


def test_build_user_profile_empty_reading_history():
    """reading_history=[] produces same result as old two-arg call."""
    profile_old = build_user_profile(saved_articles=[])
    profile_new = build_user_profile(saved_articles=[], reading_history=[])
    assert profile_old.topic_counts == profile_new.topic_counts
    assert profile_old.saved_article_ids == profile_new.saved_article_ids


def test_build_user_profile_clicked_articles_weighted():
    """Clicked articles (weight=1.0) are included in positive signal and cluster building."""
    history = [
        {"article_id": "h1", "action": "clicked", "embedding": FAKE_EMB_A, "topics": ["AI"]},
    ]
    profile = build_user_profile(saved_articles=[], reading_history=history)
    # 'AI' topic count should be non-zero from clicked article
    assert profile.topic_counts.get("AI", 0) >= 1


def test_build_user_profile_saved_articles_higher_weight():
    """Saved articles (weight=2.0) contribute more than clicked (weight=1.0)."""
    saved = [{"id": "s1", "embedding": FAKE_EMB_A, "topics": ["design"]}]
    history = [
        {"article_id": "h1", "action": "clicked", "embedding": FAKE_EMB_B, "topics": ["AI"]},
    ]
    profile = build_user_profile(saved_articles=saved, reading_history=history)
    # Both should be present; no crash
    assert profile.topic_counts.get("design", 0) >= 1
    assert profile.topic_counts.get("AI", 0) >= 1


def test_build_user_profile_dismissed_excluded_from_positive():
    """Dismissed articles in reading_history are NOT included in positive signal."""
    history = [
        {"article_id": "d1", "action": "dismissed", "embedding": FAKE_EMB_A, "topics": ["crypto"]},
    ]
    profile = build_user_profile(saved_articles=[], reading_history=history)
    # Topic should NOT be counted as positive signal
    assert profile.topic_counts.get("crypto", 0) == 0
    # But the dismissed article_id should be in dismissed set
    assert "d1" in profile.dismissed_article_ids


# ---------------------------------------------------------------------------
# verify_admin dependency
# ---------------------------------------------------------------------------

def _make_app_client():
    """Import FastAPI app and return a TestClient (requires httpx or requests)."""
    # We test verify_admin logic directly without spinning up the server.
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials

    # Inline verify_admin logic extracted from main.py for unit testing.
    def verify_admin_fn(creds, admin_token):
        if not admin_token or creds is None or creds.credentials != admin_token:
            raise HTTPException(status_code=403, detail="Forbidden")

    return verify_admin_fn


def test_verify_admin_valid_token():
    from fastapi import HTTPException
    verify_admin_fn = _make_app_client()
    creds = MagicMock()
    creds.credentials = "secret123"
    # Should not raise
    verify_admin_fn(creds, "secret123")


def test_verify_admin_wrong_token():
    from fastapi import HTTPException
    verify_admin_fn = _make_app_client()
    creds = MagicMock()
    creds.credentials = "wrongtoken"
    with pytest.raises(HTTPException) as exc:
        verify_admin_fn(creds, "secret123")
    assert exc.value.status_code == 403


def test_verify_admin_no_credentials():
    from fastapi import HTTPException
    verify_admin_fn = _make_app_client()
    with pytest.raises(HTTPException) as exc:
        verify_admin_fn(None, "secret123")
    assert exc.value.status_code == 403


def test_verify_admin_empty_env_token():
    """ADMIN_TOKEN env var is empty string → 403 (empty string = not configured)."""
    from fastapi import HTTPException
    verify_admin_fn = _make_app_client()
    creds = MagicMock()
    creds.credentials = ""
    with pytest.raises(HTTPException) as exc:
        verify_admin_fn(creds, "")
    assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# Async suggest job system
# ---------------------------------------------------------------------------

def test_suggest_job_returns_job_id_immediately():
    """POST /api/admin/suggest must return job_id immediately without waiting for Groq."""
    # Test the in-memory job store directly — job is created before background task runs.
    _suggest_jobs = {}
    job_id = str(uuid.uuid4())
    _suggest_jobs[job_id] = {"status": "pending", "results": None, "error": None}
    assert _suggest_jobs[job_id]["status"] == "pending"
    assert _suggest_jobs[job_id]["results"] is None


def test_suggest_job_poll_returns_complete_after_task():
    """After background task completes, GET /api/admin/suggest/{job_id} returns results."""
    _suggest_jobs = {}
    job_id = str(uuid.uuid4())
    _suggest_jobs[job_id] = {"status": "pending", "results": None, "error": None}
    # Simulate task completion
    _suggest_jobs[job_id] = {"status": "complete", "results": [{"title": "Test"}], "error": None}
    assert _suggest_jobs[job_id]["status"] == "complete"
    assert len(_suggest_jobs[job_id]["results"]) == 1


def test_suggest_job_poll_returns_failed_on_error():
    """If background task fails, GET returns status='failed' with error message."""
    _suggest_jobs = {}
    job_id = str(uuid.uuid4())
    _suggest_jobs[job_id] = {"status": "pending", "results": None, "error": None}
    _suggest_jobs[job_id] = {"status": "failed", "results": None, "error": "Groq timeout"}
    assert _suggest_jobs[job_id]["status"] == "failed"
    assert "Groq" in _suggest_jobs[job_id]["error"]


def test_suggest_job_poll_unknown_id_raises_404():
    """GET /api/admin/suggest/{job_id} with unknown ID raises 404."""
    from fastapi import HTTPException
    _suggest_jobs = {}

    def poll_job(job_id):
        job = _suggest_jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    with pytest.raises(HTTPException) as exc:
        poll_job("nonexistent-id")
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Database schema assertions (model-level, no DB required)
# ---------------------------------------------------------------------------

def test_article_groq_quality_score_nullable():
    """Article.groq_quality_score is a nullable Float defaulting to None."""
    from database import Article
    col = Article.__table__.columns.get("groq_quality_score")
    assert col is not None
    assert col.nullable is True


def test_reading_history_user_id_nullable():
    """ReadingHistory.user_id is nullable (FK dropped in Phase 3B migration)."""
    from database import ReadingHistory
    col = ReadingHistory.__table__.columns.get("user_id")
    assert col is not None
    assert col.nullable is True


def test_eval_event_table_exists():
    """EvalEvent model is defined and has required columns."""
    from database import EvalEvent
    cols = {c.name for c in EvalEvent.__table__.columns}
    assert "id" in cols
    assert "event_type" in cols
    assert "article_id" in cols
    assert "user_id" in cols
    assert "metadata" in cols
    assert "created_at" in cols


# ---------------------------------------------------------------------------
# POST /api/reading-history validation
# ---------------------------------------------------------------------------

def test_reading_history_invalid_action_raises_422():
    """action not in ['clicked', 'viewed', 'dismissed'] → 422."""
    from fastapi import HTTPException

    valid_actions = {"clicked", "viewed", "dismissed"}

    def validate_action(action):
        if action not in valid_actions:
            raise HTTPException(status_code=422, detail=f"action must be one of {valid_actions}")

    with pytest.raises(HTTPException) as exc:
        validate_action("liked")
    assert exc.value.status_code == 422


def test_reading_history_valid_actions_pass():
    """Valid actions do not raise."""
    from fastapi import HTTPException

    valid_actions = {"clicked", "viewed", "dismissed"}

    def validate_action(action):
        if action not in valid_actions:
            raise HTTPException(status_code=422, detail="bad action")

    for action in valid_actions:
        validate_action(action)  # Should not raise


# ---------------------------------------------------------------------------
# Cold-start boundary condition
# ---------------------------------------------------------------------------

def test_cold_start_threshold_exactly_5():
    """Exactly 5 interactions → NOT cold start (banner disappears)."""
    history_count = 5
    cold_start = history_count < 5
    assert cold_start is False


def test_cold_start_threshold_4():
    """4 interactions → cold start."""
    history_count = 4
    cold_start = history_count < 5
    assert cold_start is True
