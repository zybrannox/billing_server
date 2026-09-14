from typing import Optional

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class InvoiceItem(Base):
    """One line item on an invoice - a print/signage job is usually billed
    by area (width x height => sq ft) at a per-sq-ft rate, so each line
    captures that instead of a single flat amount. `sq_ft` and `total` are
    computed at creation time (see app/invoices/repository.py) and stored
    rather than recomputed on read: once an invoice is generated it's a
    financial record, and its line totals must stay exactly what the
    customer was billed even if the calculation logic changes later.
    """

    __tablename__ = "invoice_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    invoice_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("invoices_v1.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    width: Mapped[float] = mapped_column(Float, nullable=False)
    height: Mapped[float] = mapped_column(Float, nullable=False)
    # The unit width/height were actually entered in ("ft" or "in") - not
    # every job is naturally measured in feet (a name board is more usefully
    # "18in x 6in" than "1.5ft x 0.5ft"). `sq_ft` below is always the
    # canonical billing quantity in square feet either way (see
    # app/invoices/calculations.py's compute_line), so this only affects
    # how width/height are displayed, not how the total is computed.
    unit: Mapped[str] = mapped_column(String(4), nullable=False, default="ft")
    sq_ft: Mapped[float] = mapped_column(Float, nullable=False)
    rate: Mapped[float] = mapped_column(Float, nullable=False)
    # How many identical pieces this line bills for - `total` already has
    # this multiplied in (see app/invoices/calculations.py's compute_line),
    # stored separately so the printed invoice can show "x N" rather than
    # only the already-multiplied total.
    pieces: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    total: Mapped[float] = mapped_column(Float, nullable=False)
    # True when this line's Total was typed directly in the create form
    # (see GenerateInvoice.tsx) rather than the ordinary rate-times-area
    # flow - `rate` is still always populated either way (back-derived as
    # total ÷ area so the math stays consistent), but it was never really
    # "the rate", just a number solved for algebraically, so the invoice
    # view hides it for these rows instead of showing a number nobody
    # actually entered.
    is_manual_total: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    invoice = relationship("Invoice", back_populates="items")
