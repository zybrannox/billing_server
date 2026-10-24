from datetime import datetime
from app.datetime_utils import utcnow
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class DocumentSettings(Base):
    """The shop's branding and layout choices for every printed document
    (invoice, quotation, ...) - one row, id=1, created with the defaults
    below on first read (see app/document_settings/repository.py). Admin
    edits it from System Setup; every document renderer reads it, so a
    change applies to all of them at once.

    `template` picks the layout style; `theme` names a preset palette (resolved on the frontend - see
    src/documents/documentTheme.ts) or "custom", in which case
    `custom_color` is the accent. Only the accent is stored, never derived
    shades, so adding or retuning a preset never needs a migration.
    """

    __tablename__ = "document_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Business identity - printed in the FROM block and the footer.
    business_name: Mapped[str] = mapped_column(String(120), default="Zybrannox")
    # Brand slogan, printed under the logo.
    tagline: Mapped[Optional[str]] = mapped_column(
        String(160), nullable=True, default="Printing & Signage Services", server_default="Printing & Signage Services"
    )
    address: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, default="5/90 Melachunda Vilai, Karungal (P.O),\nKanyakumari, Tamil Nadu 629157"
    )
    phone: Mapped[Optional[str]] = mapped_column(String(40), nullable=True, default="+91 84386 08478")
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tax_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    # Uploaded logo, stored under uploads/branding/ (see service.py).
    # Null means "use the built-in logo".
    logo_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Layout style (see src/documents/documentTemplates.ts) - independent of
    # the colour `theme` below, so any template can wear any accent.
    template: Mapped[str] = mapped_column(String(20), default="classic", server_default="classic")
    theme: Mapped[str] = mapped_column(String(20), default="indigo")
    custom_color: Mapped[Optional[str]] = mapped_column(String(7), nullable=True)

    show_top_bar: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    show_payment_history: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())

    tax_label: Mapped[str] = mapped_column(String(40), default="Tax / GST")
    tax_note: Mapped[str] = mapped_column(String(80), default="As applicable")
    invoice_terms: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quotation_terms: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        default="This is an estimate, not a bill - amounts are subject to change until converted to an invoice.",
    )
    footer_message: Mapped[str] = mapped_column(String(200), default="Thank you for your business.")

    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
