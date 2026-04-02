"""
probation.py — Layer 4: Probation source evaluation and promotion.

For each source with source_type='probation' (is_active=0):
  1. Count inbound citations from link_citations table
  2. Count and average quality of articles already ingested from this domain
  3. Promote to source_type='dynamic', is_active=1 if thresholds met
  4. Remove sources in probation too long with zero citations

Thresholds:
  - PROMOTE if citations >= MIN_CITATIONS_TO_PROMOTE AND avg_quality >= MIN_QUALITY_TO_PROMOTE
  - REMOVE if probation_start < NOW() - MAX_PROBATION_DAYS AND citations == 0

Returns a stats dict: {evaluated, promoted, removed, kept}
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Minimum inbound citations required to promote a probation source
MIN_CITATIONS_TO_PROMOTE = 3
# Minimum average article quality score to promote (0.0–1.0)
MIN_QUALITY_TO_PROMOTE = 0.4
# Days before a zero-citation probation source is removed
MAX_PROBATION_DAYS = 30
# Max probation sources to evaluate per run
MAX_SOURCES_PER_RUN = 500


def _count_citations(db: Session, domain: str) -> int:
    """Count inbound citations for a domain from the link_citations table."""
    try:
        row = db.execute(
            text("SELECT COUNT(*) FROM link_citations WHERE cited_domain = :domain"),
            {"domain": domain},
        ).fetchone()
        return row[0] if row else 0
    except Exception as exc:
        logger.debug("Citation count failed for %s: %s", domain, exc)
        return 0


def _article_stats(db: Session, domain: str) -> tuple[int, Optional[float]]:
    """
    Count articles and compute average quality for a domain.
    Returns (article_count, avg_quality) where avg_quality may be None.
    """
    try:
        row = db.execute(
            text(
                """
                SELECT COUNT(*), AVG(groq_quality_score)
                FROM articles
                WHERE source_id = (
                    SELECT id FROM sources WHERE domain = :domain LIMIT 1
                )
                  AND curation_status = 'raw'
                """
            ),
            {"domain": domain},
        ).fetchone()
        if row:
            count = row[0] or 0
            avg_q = float(row[1]) if row[1] is not None else None
            return count, avg_q
        return 0, None
    except Exception as exc:
        logger.debug("Article stats failed for %s: %s", domain, exc)
        return 0, None


def _promote_source(db: Session, source_id: str, domain: str) -> bool:
    """Promote a probation source to dynamic/active. Returns True on success."""
    try:
        db.execute(
            text(
                """
                UPDATE sources
                SET source_type = 'dynamic',
                    is_active = 1
                WHERE id = :id
                """
            ),
            {"id": source_id},
        )
        logger.info("Promoted probation source to dynamic: %s", domain)
        return True
    except Exception as exc:
        logger.warning("Promotion failed for %s: %s", domain, exc)
        return False


def _remove_source(db: Session, source_id: str, domain: str) -> bool:
    """Remove a stale probation source with no citations. Returns True on success."""
    try:
        # Remove any lingering citations first (FK safety)
        db.execute(
            text("DELETE FROM link_citations WHERE cited_domain = :domain"),
            {"domain": domain},
        )
        db.execute(
            text("DELETE FROM sources WHERE id = :id"),
            {"id": source_id},
        )
        logger.info("Removed stale probation source: %s", domain)
        return True
    except Exception as exc:
        logger.warning("Removal failed for %s: %s", domain, exc)
        return False


def evaluate_probation_sources(
    db: Session,
    max_sources: int = MAX_SOURCES_PER_RUN,
) -> dict:
    """
    Evaluate all probation sources and promote or remove as appropriate.

    Returns aggregate stats dict: {evaluated, promoted, removed, kept}
    """
    stats = {"evaluated": 0, "promoted": 0, "removed": 0, "kept": 0}

    try:
        rows = db.execute(
            text(
                """
                SELECT id, domain, probation_start
                FROM sources
                WHERE source_type = 'probation'
                  AND is_active = 0
                ORDER BY probation_start ASC NULLS LAST
                LIMIT :limit
                """
            ),
            {"limit": max_sources},
        ).fetchall()
    except Exception as exc:
        logger.error("Failed to query probation sources: %s", exc)
        return {**stats, "errors": 1}

    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_PROBATION_DAYS)
    now = datetime.now(timezone.utc)

    for row in rows:
        source_id, domain, probation_start = row[0], row[1], row[2]
        stats["evaluated"] += 1

        citation_count = _count_citations(db, domain)
        article_count, avg_quality = _article_stats(db, domain)

        logger.debug(
            "Evaluating probation source %s: citations=%d articles=%d avg_quality=%s",
            domain,
            citation_count,
            article_count,
            avg_quality,
        )

        # Determine effective quality — use avg article quality or fallback
        effective_quality = avg_quality if avg_quality is not None else 0.0

        # Promote if thresholds met
        if (
            citation_count >= MIN_CITATIONS_TO_PROMOTE
            and effective_quality >= MIN_QUALITY_TO_PROMOTE
        ):
            ok = _promote_source(db, source_id, domain)
            if ok:
                stats["promoted"] += 1
            else:
                stats["kept"] += 1
            try:
                db.commit()
            except Exception as exc:
                logger.warning("Commit failed after promotion of %s: %s", domain, exc)
                db.rollback()
            continue

        # Remove if past max probation age with zero citations
        if citation_count == 0 and probation_start is not None:
            # Normalize timezone
            ps = probation_start
            if ps.tzinfo is None:
                ps = ps.replace(tzinfo=timezone.utc)
            if ps < cutoff:
                ok = _remove_source(db, source_id, domain)
                if ok:
                    stats["removed"] += 1
                else:
                    stats["kept"] += 1
                try:
                    db.commit()
                except Exception as exc:
                    logger.warning("Commit failed after removal of %s: %s", domain, exc)
                    db.rollback()
                continue

        # Keep in probation
        stats["kept"] += 1

    logger.info(
        "Probation evaluation complete: %d evaluated, %d promoted, %d removed, %d kept",
        stats["evaluated"],
        stats["promoted"],
        stats["removed"],
        stats["kept"],
    )
    return stats
