from typing import Optional

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class QuotationItem(Base):
    """One line item on a quotation - identical shape to InvoiceItem (see
    app/entities/invoice_item.py), since a quotation prices a job the exact
    same way an invoice bills one (width x height => sq ft, at a per-sq-ft
    rate). Kept as its own table rather than reusing invoice_items so a
    quotation's numbers stay stable even if the job's real dimensions
    change once it's actually invoiced.
    """

    __tablename__ = "quotation_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    quotation_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quotations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    width: Mapped[float] = mapped_column(Float, nullable=False)
    height: Mapped[float] = mapped_column(Float, nullable=False)
    # See InvoiceItem.unit - carried straight over on conversion.
    unit: Mapped[str] = mapped_column(String(4), nullable=False, default="ft")
    sq_ft: Mapped[float] = mapped_column(Float, nullable=False)
    rate: Mapped[float] = mapped_column(Float, nullable=False)
    # See InvoiceItem.pieces - carried straight over on conversion (see
    # app/quotations/repository.py's convert_quotation_to_invoice).
    pieces: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total: Mapped[float] = mapped_column(Float, nullable=False)
    is_manual_total: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    quotation = relationship("Quotation", back_populates="items")
