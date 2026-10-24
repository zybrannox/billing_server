from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.datetime_utils import utcnow


class AuditLog(Base):
    """Append-only record of money and destructive actions (payments,
    cancellations, deletes, lockouts).

    Rows are only ever inserted. In Postgres the table is also protected by a
    trigger (see the phase-4 migration) that rejects UPDATE and DELETE, so
    even a bug or a direct SQL session can't rewrite history.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    # Username of the staff member, "client:<account id>" for the portal, or
    # "system" for automatic events.
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    # "<entity>.<verb>", e.g. "invoice.cancel", "invoice.payment", "customer.delete".
    action: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Small JSON snapshot: a human label for the entity plus whatever changed.
    detail: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)

    __table_args__ = (Index("ix_audit_log_entity", "entity_type", "entity_id"),)
