from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.database import get_db
from app.pagination import page_count

from .model import AuditLogListResponse
from .service import list_entries

router = APIRouter(prefix="/audit-log", tags=["Audit"])


@router.get("/", response_model=AuditLogListResponse)
def list_audit_log(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    actor: Optional[str] = None,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    rows, total = list_entries(db, page, page_size, action, entity_type, entity_id, actor)
    return AuditLogListResponse(
        items=rows, total=total, page=page, page_size=page_size, total_pages=page_count(total, page_size)
    )
