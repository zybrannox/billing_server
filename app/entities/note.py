from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.datetime_utils import utcnow


class Note(Base):
    """A quick note about a job, to tick off when it's done and turn into a bill."""

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Optional: often jotted down before anyone's decided who it's for.
    customer_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    is_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false", index=True)
    done_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    done_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # The invoice this note became. Cleared if that invoice is deleted, so the
    # note can be billed again.
    invoice_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("invoices_v1.id", ondelete="SET NULL"), nullable=True, index=True
    )

    customer = relationship("Customer")
    invoice = relationship("Invoice")

    @property
    def customer_name(self) -> Optional[str]:
        return f"{self.customer.first_name} {self.customer.last_name}".strip() if self.customer else None

    @property
    def invoice_number(self) -> Optional[str]:
        return self.invoice.invoice_number if self.invoice else None
