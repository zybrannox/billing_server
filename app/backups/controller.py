from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.audit.service import record as record_audit
from app.auth.dependencies import require_admin
from app.database import get_db
from app.rate_limiting import limiter

from . import service
from .model import BackupStatusRead

# Admin-only. Reports dates, sizes and yes/no answers, never file paths.
router = APIRouter(prefix="/backups", tags=["Backups"])


@router.get("", response_model=BackupStatusRead)
def get_backup_status(_admin: dict = Depends(require_admin)):
    return service.status()


@router.post("/run", response_model=BackupStatusRead)
@limiter.limit("5/hour")
def run_backup(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    # Sync handler on purpose: pg_dump blocks, so FastAPI runs it in its worker
    # thread pool and the event loop keeps serving everyone else.
    service.run_backup()
    record_audit(db, _admin["username"], "backup.run", "backup", None, {"label": "Database"})
    return service.status()
