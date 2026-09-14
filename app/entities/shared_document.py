from datetime import datetime
from sqlalchemy import String, Integer, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class SharedDocument(Base):
    """A public, unguessable link to a generated invoice/quotation PDF -
    lets that document be opened by anyone with the link (a customer in
    WhatsApp, say - see app/shared_documents), without them needing a
    Zybrannox account the way the regular /admin/invoices/:id page does.

    One row per (document_type, document_id): sharing the same invoice
    again re-uses its existing token/URL and just overwrites the stored
    file, rather than minting a new link (and orphaning the old file)
    every time - the invoice's own status/amount can change after it was
    first shared (paid, discounted), so the file is refreshed each share
    rather than frozen at whatever it looked like the first time.
    """

    __tablename__ = "shared_documents"
    __table_args__ = (
        UniqueConstraint("document_type", "document_id", name="uq_shared_document_type_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # Long enough to be practically unguessable (see secrets.token_urlsafe
    # in repository.py) - this, not document_id, is what the public URL
    # exposes, so a customer's invoice can't be enumerated by guessing
    # sequential ids.
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    document_type: Mapped[str] = mapped_column(String(20), nullable=False)  # "invoice" | "quotation"
    document_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # Filename on disk under UPLOAD_DIR/shared_documents/ - not the same
    # as `token`, so rotating naming schemes later wouldn't require
    # renaming every file already on disk.
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # What the recipient's browser/download shows as the file's name -
    # "Invoice-INV-2026-00042.pdf", not the opaque on-disk filename.
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
