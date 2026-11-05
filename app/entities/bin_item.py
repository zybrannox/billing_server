from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, BigInteger, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.datetime_utils import utcnow


class BinItem(Base):
    """Something deleted, kept for a while in case it was a mistake.

    Deleting removes the real rows, so no list, report or total anywhere has to
    remember to skip them; `snapshot` holds them (and everything that belonged to
    them) so restoring can put back the same records. See app/bin/service.py.
    """

    __tablename__ = "bin_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # "project", "file", "invoice", "quotation", "customer", "company", "employee"
    item_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # The id it had, for the audit trail.
    item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(500), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    deleted_by: Mapped[str] = mapped_column(String(100), nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
