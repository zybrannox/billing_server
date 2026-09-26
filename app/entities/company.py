from typing import Optional
from datetime import datetime

from sqlalchemy import String, Float, Integer, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Company(Base):
    """A B2B business account - multiple Customer rows (see
    entities/customer.py's company_id) can belong to one Company, sharing
    its billing terms (payment_terms_days, credit_limit) instead of each
    contact being invoiced independently. No `relationship()` here,
    matching Customer's own style - Customer.company_id is just a plain FK,
    joined explicitly in app/companies/service.py rather than traversed via
    the ORM, same as how Project/Invoice already relate to Customer.
    """

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    billing_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    billing_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Days after an invoice is raised before it's due (NET-15/30/60, etc.) -
    # 0 means due on receipt, same as a customer with no company at all.
    # See app/invoices/repository.py's create_invoice, which auto-defaults
    # an invoice's due_date from this when the caller didn't set one.
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Display-only in this pass - shown on the company profile page against
    # its current outstanding balance, not enforced at invoice-creation
    # time. Null means no limit is tracked.
    credit_limit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
