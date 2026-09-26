from typing import Optional
from datetime import datetime

from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class JobRequest(Base):
    """New work a client submits through the portal, before staff has
    created any Project for it (see app/job_requests). No relationship() -
    customer_id/project_id are plain FKs, joined explicitly, matching
    Customer/Company's style rather than Project's older relationship()
    one.
    """

    __tablename__ = "job_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The specific client who filed it - not the whole company, even if
    # they're a company contact (see app/job_requests/service.py).
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # Set once staff converts this request into a real, billable Project -
    # SET NULL (not CASCADE) so deleting the resulting project doesn't
    # silently delete the client's original request/history.
    project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
