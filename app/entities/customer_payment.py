from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.datetime_utils import utcnow


class CustomerPayment(Base):
    """Money a customer handed over in one go (say ₹8,000 by UPI), recorded
    against the customer rather than one invoice.

    It reaches invoices through the ordinary payment history: each invoice it
    pays gets an InvoicePayment row pointing back here (customer_payment_id), so
    invoice balances, statuses, the Invoices page and the Statement keep working
    from that one ledger. Nothing about how much of it is used is stored: the
    unused part (the customer's credit) is always `amount` minus the sum of
    those rows - see app/customer_payments/service.py - so it can't drift.
    """

    __tablename__ = "customer_payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(30), nullable=False)
    payment_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # When the customer paid, which can be earlier than when it was entered.
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    recorded_by: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
