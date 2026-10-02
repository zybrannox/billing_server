from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InvoicePayment(Base):
    """One entry in an invoice's payment history. Written by the repository
    layer whenever an invoice's `advance_amount` (its running total of money
    received - see Invoice.balance_due) changes, so the history always sums
    to that total: the advance taken at creation, each recorded instalment,
    the final mark-paid settlement. `amount` is signed - an admin correcting
    an advance downward shows up as a negative adjustment rather than the
    history silently disagreeing with the balance.
    """

    __tablename__ = "invoice_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    invoice_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("invoices_v1.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    payment_method: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    payment_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    paid_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    recorded_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
