from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.invoices.repository import get_invoice
from app.quotations.repository import get_quotation
from . import repository


def service_create_invoice_share_link(
    db: Session, invoice_id: int, file_bytes: bytes, base_url: str
) -> str:
    invoice = get_invoice(db, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    doc = repository.upsert(
        db, "invoice", invoice_id, file_bytes, f"Invoice-{invoice.invoice_number}.pdf"
    )
    # base_url (from FastAPI's Request.base_url) already reflects whatever
    # host actually served this request - localhost:8000 in dev,
    # workspace-api.zybrannox.com in production - so the returned link
    # works correctly wherever the backend is deployed without the
    # frontend needing to know or configure that domain itself.
    return f"{base_url}public/documents/{doc.token}"


def service_create_quotation_share_link(
    db: Session, quotation_id: int, file_bytes: bytes, base_url: str
) -> str:
    quotation = get_quotation(db, quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    doc = repository.upsert(
        db, "quotation", quotation_id, file_bytes, f"Quotation-{quotation.quotation_number}.pdf"
    )
    return f"{base_url}public/documents/{doc.token}"


def service_get_document_path(db: Session, token: str) -> tuple[Path, str]:
    doc = repository.get_by_token(db, token)
    if not doc:
        raise HTTPException(status_code=404, detail="This link is invalid or has expired")
    path = repository.UPLOAD_DIR / doc.filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="This link is invalid or has expired")
    return path, doc.display_name
