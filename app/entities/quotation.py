from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, Float, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Quotation(Base):
    """A pre-invoice estimate given to a customer before any project is
    committed to (see app/quotations/ - mirrors the Invoice/InvoiceItem
    pattern closely). Unlike an Invoice, a Quotation is NOT tied to a
    Project - the whole point is to price out a job the customer hasn't
    said yes to yet, so there's nothing to link to. Once accepted, it can
    be converted (see service_convert) into a real Project + Invoice,
    which is when converted_project_id/converted_invoice_id get set.
    """

    __tablename__ = "quotations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    quotation_number: Mapped[Optional[str]] = mapped_column(String(50), unique=True, index=True, nullable=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id"), nullable=False)
    # Free text, same as Project.project_type - not a closed enum (see
    # admin/pages/SystemSetup.tsx's admin-managed project type catalog).
    project_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    subtotal: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    discount_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    amount: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    # pending -> accepted -> converted, or pending -> rejected (terminal).
    # "expired" is never stored - it's derived client-side from valid_until
    # vs now while still pending, purely a display badge, so there's no
    # background job needed to flip it.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    # Set together once this quotation is converted (see service_convert) -
    # the audit trail of exactly what it became.
    converted_project_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("projects.id"), nullable=True
    )
    converted_invoice_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("invoices_v1.id"), nullable=True
    )

    customer = relationship("Customer")
    converted_project = relationship("Project")
    converted_invoice = relationship("Invoice")
    items = relationship(
        "QuotationItem",
        back_populates="quotation",
        cascade="all, delete-orphan",
        order_by="QuotationItem.sort_order",
    )

    @property
    def customer_name(self) -> Optional[str]:
        if self.customer:
            return f"{self.customer.first_name} {self.customer.last_name}"
        return None
