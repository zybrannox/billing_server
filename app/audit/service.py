import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.entities import AuditLog

logger = logging.getLogger("app.audit")


def record(
    db: Session,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: Optional[int] = None,
    detail: Optional[dict[str, Any]] = None,
) -> None:
    """Append one audit row (and commit it).

    Called by the controllers *after* the action succeeded. A failure to write
    the audit row is logged but never fails the user's request - the money or
    deletion has already happened and must not appear to have failed.
    """
    try:
        db.add(AuditLog(actor=actor, action=action, entity_type=entity_type, entity_id=entity_id, detail=detail))
        db.commit()
    except Exception:  # pragma: no cover - defensive
        db.rollback()
        logger.exception("could not write audit row %s %s#%s", action, entity_type, entity_id)


def list_entries(
    db: Session,
    page: int,
    page_size: int,
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    actor: Optional[str] = None,
):
    from sqlalchemy import func

    query = select(AuditLog)
    count = select(func.count(AuditLog.id))
    for column, value in (
        (AuditLog.action, action),
        (AuditLog.entity_type, entity_type),
        (AuditLog.entity_id, entity_id),
        (AuditLog.actor, actor),
    ):
        if value is not None:
            query = query.where(column == value)
            count = count.where(column == value)
    total = db.execute(count).scalar_one()
    rows = db.execute(
        query.order_by(AuditLog.at.desc(), AuditLog.id.desc()).offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()
    return rows, total


def label_of(db: Session, model, entity_id: int, attribute: str) -> Optional[str]:
    """A human label for an entity about to be deleted (its number or name),
    read before the delete so the audit row still says what was removed."""
    row = db.get(model, entity_id)
    return str(getattr(row, attribute)) if row is not None else None
