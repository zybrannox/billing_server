from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.audit.service import record as record_audit
from app.auth.dependencies import require_admin
from app.database import get_db
from app.entities import BinItem
from app.errors import NotFound

from . import service
from .model import BinItemRead, BinListResponse

router = APIRouter(prefix="/bin", tags=["Bin"])


@router.get("/", response_model=BinListResponse)
def list_bin(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    item_type: Optional[str] = None,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    # Also runs on a daily schedule; here too, so nothing past its date is ever
    # offered for restoring, if the server was off when the job was due.
    service.erase_expired(db)

    query = db.query(BinItem)
    if item_type:
        query = query.filter(BinItem.item_type == item_type)
    total = query.count()
    items = (
        query.order_by(BinItem.deleted_at.desc(), BinItem.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    counts = db.query(BinItem.item_type, func.count(BinItem.id)).group_by(BinItem.item_type).all()
    return {
        "items": items,
        "total": total,
        "counts": [{"item_type": t, "count": c} for t, c in counts],
        "total_size_bytes": db.query(func.coalesce(func.sum(BinItem.size_bytes), 0)).scalar(),
        "retention_days": service.BIN_RETENTION_DAYS,
    }


@router.post("/{item_id}/restore", response_model=BinItemRead)
def restore_item(item_id: int, db: Session = Depends(get_db), _admin: dict = Depends(require_admin)):
    item = db.get(BinItem, item_id)
    if not item:
        raise NotFound("Bin item")
    result = BinItemRead.model_validate(item)
    original_id, item_type = item.item_id, item.item_type
    service.restore(db, item_id)
    record_audit(db, _admin["username"], "bin.restore", service.log_type(item_type), original_id, {"label": result.label})
    return result


@router.delete("/{item_id}")
def erase_item(item_id: int, db: Session = Depends(get_db), _admin: dict = Depends(require_admin)):
    item = db.get(BinItem, item_id)
    if not item:
        raise NotFound("Bin item")
    label, item_type, original_id = item.label, item.item_type, item.item_id
    service.erase(db, item)
    record_audit(db, _admin["username"], "bin.erase", service.log_type(item_type), original_id, {"label": label})
    return {"message": "Permanently deleted"}


@router.delete("/")
def empty_bin(db: Session = Depends(get_db), _admin: dict = Depends(require_admin)):
    count = service.empty(db)
    record_audit(db, _admin["username"], "bin.empty", "bin", None, {"label": f"{count} items"})
    return {"message": f"{count} items permanently deleted", "count": count}
