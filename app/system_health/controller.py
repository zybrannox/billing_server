from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.database import get_db
from app.database.slow_queries import RECENT_SLOW_QUERIES
from app.rate_limiting import limiter

from . import collector
from .diagnosis import diagnose
from .history import history
from .metrics import request_metrics
from .model import HealthPointRead, SystemHealthRead

# Admin-only and strictly read-only: it reports numbers and role labels, never
# command lines, environment variables or file paths.
router = APIRouter(prefix="/system-health", tags=["System health"])


def _active_uploads() -> int:
    from app.project_files import chunked

    return len(chunked._sessions)


@router.get("", response_model=SystemHealthRead)
@limiter.limit("60/minute")
def get_system_health(request: Request, response: Response, _admin: dict = Depends(require_admin)):
    # Sync handler on purpose: psutil's process scan blocks, so FastAPI runs it
    # in its worker thread pool and the event loop keeps serving everyone else.
    response.headers["Cache-Control"] = "no-store"
    live = collector.live_snapshot()
    storage, refreshing = collector.storage_report()
    performance = request_metrics.summary(minutes=15)
    slow = sorted(RECENT_SLOW_QUERIES, key=lambda q: q["at"], reverse=True)
    uploads = _active_uploads()
    return {
        "generated_at": datetime.now(timezone.utc),
        "machine": live["machine"],
        "processes": live["processes"],
        "pool": live["pool"],
        "storage": {
            "computed_at": datetime.fromtimestamp(storage.computed_at, timezone.utc) if storage else None,
            "refreshing": refreshing,
            "complete": storage.complete if storage else True,
            "folders": storage.folders if storage else [],
            "database": storage.database if storage else None,
        },
        "performance": performance,
        "slow_queries": slow,
        "active_uploads": uploads,
        "diagnosis": diagnose(live["machine"], live["processes"], live["pool"], performance, slow, uploads),
    }


@router.get("/history", response_model=list[HealthPointRead])
@limiter.limit("30/minute")
def get_system_health_history(
    request: Request,
    response: Response,
    minutes: int = Query(60, ge=5, le=7 * 24 * 60),
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    response.headers["Cache-Control"] = "no-store"
    return history(db, minutes)
