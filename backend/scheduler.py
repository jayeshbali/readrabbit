"""
scheduler.py — APScheduler wiring for all pipeline layers.

Schedules:
  Layer 1 (feed_crawler):       every CRAWLER_INTERVAL_HRS  hours (default: 6)
  Layer 2 (link_graph):         every LINK_GRAPH_INTERVAL_HRS hours (default: 2)
  Layer 3 (aggregator_tap):     every AGGREGATOR_INTERVAL_HRS hours (default: 4)
  Layer 4 (probation):          every PROBATION_INTERVAL_HRS hours (default: 24)

Override intervals via environment variables.

Public API:
  start_scheduler(db_factory)  — call from FastAPI lifespan startup
  stop_scheduler()             — call from FastAPI lifespan shutdown
  get_scheduler_status()       — returns last-run stats per task
"""

import logging
import os
import traceback
from datetime import datetime, timezone
from typing import Callable, Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configurable intervals (hours) — override via env vars
# ---------------------------------------------------------------------------

CRAWLER_INTERVAL_HRS = float(os.getenv("CRAWLER_INTERVAL_HRS", "6"))
LINK_GRAPH_INTERVAL_HRS = float(os.getenv("LINK_GRAPH_INTERVAL_HRS", "2"))
AGGREGATOR_INTERVAL_HRS = float(os.getenv("AGGREGATOR_INTERVAL_HRS", "4"))
PROBATION_INTERVAL_HRS = float(os.getenv("PROBATION_INTERVAL_HRS", "24"))

# ---------------------------------------------------------------------------
# Run-stat tracking — updated after each scheduled run
# ---------------------------------------------------------------------------

_last_run: dict[str, dict] = {
    "feed_crawler": {"last_ran": None, "last_stats": None, "last_error": None},
    "link_graph": {"last_ran": None, "last_stats": None, "last_error": None},
    "aggregator_tap": {"last_ran": None, "last_stats": None, "last_error": None},
    "probation": {"last_ran": None, "last_stats": None, "last_error": None},
}

_scheduler: Optional[BackgroundScheduler] = None


# ---------------------------------------------------------------------------
# Job wrappers
# ---------------------------------------------------------------------------

def _run_feed_crawler(db_factory: Callable) -> None:
    """Run Layer 1: RSS/Atom feed crawl."""
    from feed_crawler import crawl_all_sources

    db = db_factory()
    try:
        logger.info("Scheduler: starting feed_crawler run")
        stats = crawl_all_sources(db)
        _last_run["feed_crawler"]["last_ran"] = datetime.now(timezone.utc).isoformat()
        _last_run["feed_crawler"]["last_stats"] = stats
        _last_run["feed_crawler"]["last_error"] = None
        logger.info(
            "Scheduler: feed_crawler done — %d sources, %d new articles",
            stats.get("sources_crawled", 0),
            stats.get("new_articles", 0),
        )
    except Exception as exc:
        _last_run["feed_crawler"]["last_ran"] = datetime.now(timezone.utc).isoformat()
        _last_run["feed_crawler"]["last_error"] = str(exc)
        logger.error("Scheduler: feed_crawler failed: %s\n%s", exc, traceback.format_exc())
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        try:
            db.close()
        except Exception:
            pass


def _run_link_graph(db_factory: Callable) -> None:
    """Run Layer 2: Link-graph expansion."""
    from link_graph import expand_link_graph

    db = db_factory()
    try:
        logger.info("Scheduler: starting link_graph run")
        stats = expand_link_graph(db)
        _last_run["link_graph"]["last_ran"] = datetime.now(timezone.utc).isoformat()
        _last_run["link_graph"]["last_stats"] = stats
        _last_run["link_graph"]["last_error"] = None
        logger.info(
            "Scheduler: link_graph done — %d articles scanned, %d new sources",
            stats.get("articles_scanned", 0),
            stats.get("new_sources", 0),
        )
    except Exception as exc:
        _last_run["link_graph"]["last_ran"] = datetime.now(timezone.utc).isoformat()
        _last_run["link_graph"]["last_error"] = str(exc)
        logger.error("Scheduler: link_graph failed: %s\n%s", exc, traceback.format_exc())
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        try:
            db.close()
        except Exception:
            pass


def _run_aggregator_tap(db_factory: Callable) -> None:
    """Run Layer 3: Aggregator tap (HN, Lobsters, Pinboard, Reddit)."""
    from aggregator_tap import tap_aggregators

    db = db_factory()
    try:
        logger.info("Scheduler: starting aggregator_tap run")
        stats = tap_aggregators(db)
        _last_run["aggregator_tap"]["last_ran"] = datetime.now(timezone.utc).isoformat()
        _last_run["aggregator_tap"]["last_stats"] = stats
        _last_run["aggregator_tap"]["last_error"] = None
        logger.info(
            "Scheduler: aggregator_tap done — %d discovered, %d ingested",
            stats.get("total_discovered", 0),
            stats.get("total_ingested", 0),
        )
    except Exception as exc:
        _last_run["aggregator_tap"]["last_ran"] = datetime.now(timezone.utc).isoformat()
        _last_run["aggregator_tap"]["last_error"] = str(exc)
        logger.error("Scheduler: aggregator_tap failed: %s\n%s", exc, traceback.format_exc())
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        try:
            db.close()
        except Exception:
            pass


def _run_probation(db_factory: Callable) -> None:
    """Run Layer 4: Probation source evaluation."""
    from probation import evaluate_probation_sources

    db = db_factory()
    try:
        logger.info("Scheduler: starting probation evaluation run")
        stats = evaluate_probation_sources(db)
        _last_run["probation"]["last_ran"] = datetime.now(timezone.utc).isoformat()
        _last_run["probation"]["last_stats"] = stats
        _last_run["probation"]["last_error"] = None
        logger.info(
            "Scheduler: probation done — %d evaluated, %d promoted, %d removed",
            stats.get("evaluated", 0),
            stats.get("promoted", 0),
            stats.get("removed", 0),
        )
    except Exception as exc:
        _last_run["probation"]["last_ran"] = datetime.now(timezone.utc).isoformat()
        _last_run["probation"]["last_error"] = str(exc)
        logger.error("Scheduler: probation failed: %s\n%s", exc, traceback.format_exc())
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        try:
            db.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def start_scheduler(db_factory: Callable) -> None:
    """
    Start the background scheduler with all pipeline jobs.

    db_factory should be a zero-argument callable that returns a new SQLAlchemy
    Session — typically `database.SessionLocal`.
    """
    global _scheduler

    if _scheduler is not None and _scheduler.running:
        logger.warning("Scheduler already running — ignoring start_scheduler call")
        return

    _scheduler = BackgroundScheduler(timezone="UTC")

    _scheduler.add_job(
        func=_run_feed_crawler,
        trigger=IntervalTrigger(hours=CRAWLER_INTERVAL_HRS),
        args=[db_factory],
        id="feed_crawler",
        name="Layer 1: Feed Crawler",
        replace_existing=True,
        misfire_grace_time=3600,  # tolerate up to 1h late start
    )

    _scheduler.add_job(
        func=_run_link_graph,
        trigger=IntervalTrigger(hours=LINK_GRAPH_INTERVAL_HRS),
        args=[db_factory],
        id="link_graph",
        name="Layer 2: Link Graph",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    _scheduler.add_job(
        func=_run_aggregator_tap,
        trigger=IntervalTrigger(hours=AGGREGATOR_INTERVAL_HRS),
        args=[db_factory],
        id="aggregator_tap",
        name="Layer 3: Aggregator Tap",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    _scheduler.add_job(
        func=_run_probation,
        trigger=IntervalTrigger(hours=PROBATION_INTERVAL_HRS),
        args=[db_factory],
        id="probation",
        name="Layer 4: Probation Evaluator",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    _scheduler.start()
    logger.info(
        "Scheduler started — intervals: crawler=%.1fh, link_graph=%.1fh, "
        "aggregator=%.1fh, probation=%.1fh",
        CRAWLER_INTERVAL_HRS,
        LINK_GRAPH_INTERVAL_HRS,
        AGGREGATOR_INTERVAL_HRS,
        PROBATION_INTERVAL_HRS,
    )


def stop_scheduler() -> None:
    """Shut down the background scheduler gracefully."""
    global _scheduler

    if _scheduler is None:
        return

    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    _scheduler = None


def run_task_now(task_name: str, db_factory: Callable) -> dict:
    """
    Manually trigger a single pipeline task by name.

    task_name: one of 'feed_crawler', 'link_graph', 'aggregator_tap', 'probation'

    Returns the last-run stats dict for that task after it completes.
    Raises ValueError for unknown task names.
    """
    dispatch = {
        "feed_crawler": _run_feed_crawler,
        "link_graph": _run_link_graph,
        "aggregator_tap": _run_aggregator_tap,
        "probation": _run_probation,
    }

    if task_name not in dispatch:
        raise ValueError(
            f"Unknown task '{task_name}'. Valid tasks: {list(dispatch.keys())}"
        )

    dispatch[task_name](db_factory)
    return _last_run[task_name]


def get_scheduler_status() -> dict:
    """
    Return current scheduler status and last-run stats for all tasks.

    Used by the GET /admin/pipeline/status endpoint.
    """
    return {
        "scheduler_running": _scheduler is not None and _scheduler.running,
        "intervals_hours": {
            "feed_crawler": CRAWLER_INTERVAL_HRS,
            "link_graph": LINK_GRAPH_INTERVAL_HRS,
            "aggregator_tap": AGGREGATOR_INTERVAL_HRS,
            "probation": PROBATION_INTERVAL_HRS,
        },
        "last_run": _last_run,
    }
