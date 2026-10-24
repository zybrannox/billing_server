"""Minute-by-minute snapshots, written by the scheduler, never by a request."""
import logging
from datetime import timedelta

from sqlalchemy import delete, select

from app.database import SessionLocal
from app.datetime_utils import utcnow
from app.entities import SystemMetric

from . import collector
from .metrics import request_metrics

logger = logging.getLogger("app.system_health")
RETENTION_DAYS = 7


def record_snapshot() -> None:
    """Never raises: a monitoring hiccup must not disturb the scheduler."""
    try:
        live = collector.live_snapshot()
        machine, minute = live["machine"], request_metrics.last_minute()
        app_mb = sum(
            c["memory_mb"] for c in live["processes"]["components"] if c["memory_known"] and c["role"] != "Public tunnel (cloudflared)"
        )
        pool = live["pool"]
        with SessionLocal() as db:
            db.add(SystemMetric(
                memory_available_pct=machine["memory_available_pct"],
                swap_used_mb=machine["swap_used_mb"],
                load_per_core=machine["load_per_core"],
                disk_free_pct=machine["disk_free_pct"],
                app_memory_mb=app_mb,
                db_connections_in_use=pool["in_use"] if pool else None,
                requests=minute["requests"],
                errors=minute["errors"],
                p95_ms=minute["p95_ms"],
            ))
            db.execute(delete(SystemMetric).where(SystemMetric.at < utcnow() - timedelta(days=RETENTION_DAYS)))
            db.commit()
    except Exception:
        logger.exception("could not record a health snapshot")


def refresh_storage_safely() -> None:
    try:
        collector.refresh_storage()
    except Exception:
        logger.exception("could not refresh storage sizes")


def history(db, minutes: int) -> list[SystemMetric]:
    """At most ~120 points however long the window, so the chart stays light."""
    since = utcnow() - timedelta(minutes=minutes)
    rows = list(db.execute(select(SystemMetric).where(SystemMetric.at >= since).order_by(SystemMetric.at)).scalars())
    if len(rows) > 120:
        step = len(rows) / 120
        rows = [rows[int(i * step)] for i in range(120)]
    return rows


def register_jobs(scheduler) -> None:
    from apscheduler.triggers.interval import IntervalTrigger

    scheduler.add_job(record_snapshot, IntervalTrigger(seconds=60), id="health_snapshot",
                      replace_existing=True, max_instances=1, coalesce=True)
    scheduler.add_job(refresh_storage_safely, IntervalTrigger(minutes=10), id="storage_scan",
                      replace_existing=True, max_instances=1, coalesce=True)
    # First storage numbers shortly after boot instead of after ten minutes.
    from datetime import datetime, timezone

    scheduler.add_job(refresh_storage_safely, "date",
                      run_date=datetime.now(timezone.utc) + timedelta(seconds=20), id="storage_scan_boot",
                      replace_existing=True)
