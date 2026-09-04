import enum
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base

class InvoiceStatus(enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    CANCELLED = "cancelled"

class Invoice(Base):
    __tablename__ = "invoices_v1"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(Integer, ForeignKey("projects.id"), nullable=False)
    invoice_number: Mapped[Optional[str]] = mapped_column(String(50), unique=True, index=True, nullable=True)
    # `subtotal` is the raw sum of line items; `amount` is what's actually
    # owed after `discount_amount` is taken off (subtotal - discount) -
    # every other computation (balance_due, the Billing list's "Amount"
    # column) uses `amount`, since that's the real total, not the
    # pre-discount figure.
    subtotal: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    discount_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    due_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    # Advance payment - recorded manually by an admin (no payment gateway
    # involved), typically taken upfront before work starts. 0 = none
    # recorded. payment_method/reference describe how that advance (or,
    # once settled, the full amount) was received - both optional since an
    # invoice can exist with no payment info yet.
    advance_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    payment_method: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    payment_reference: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Relationships
    project = relationship("Project")
    # Line items drive `subtotal` (see app/invoices/repository.py's
    # create_invoice) - deleting an invoice takes its items with it,
    # both at the DB level (ondelete=CASCADE on the FK) and the ORM
    # level (so an in-session delete doesn't need a separate flush first).
    items = relationship(
        "InvoiceItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceItem.sort_order",
    )

    @property
    def balance_due(self) -> float:
        return round(max(0.0, self.amount - (self.advance_amount or 0)), 2)

    # The Billing list otherwise shows nothing but an auto-numbered
    # INV-2026-XXXXX - no way to tell whose order it even is without
    # opening each one. Mirrors Project.customer_name's exact pattern.
    @property
    def customer_name(self) -> Optional[str]:
        if self.project and self.project.customer:
            return f"{self.project.customer.first_name} {self.project.customer.last_name}"
        return None

    @property
    def project_type(self) -> Optional[str]:
        return self.project.project_type if self.project else None
