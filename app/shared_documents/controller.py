from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db

from .model import ShareLinkResponse
from .service import (
    service_create_invoice_share_link,
    service_create_quotation_share_link,
    service_get_document_path,
)

router = APIRouter(tags=["Shared Documents"])


# Open to any authenticated user, same as generating the invoice/quotation
# itself - sharing your own already-generated document isn't a financial-
# oversight action that needs admin-only gating. `file` is the exact PDF
# already rendered client-side (see utils/generateInvoicePdf.ts) - there's
# no server-side renderer for the same styled document, so the browser's
# own render is uploaded here rather than redone from scratch.
@router.post("/invoices/{invoice_id}/share-link", response_model=ShareLinkResponse)
async def create_invoice_share_link(
    invoice_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    file_bytes = await file.read()
    url = service_create_invoice_share_link(db, invoice_id, file_bytes, str(request.base_url))
    return ShareLinkResponse(url=url)


@router.post("/quotations/{quotation_id}/share-link", response_model=ShareLinkResponse)
async def create_quotation_share_link(
    quotation_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    file_bytes = await file.read()
    url = service_create_quotation_share_link(db, quotation_id, file_bytes, str(request.base_url))
    return ShareLinkResponse(url=url)


# Deliberately no auth dependency at all - this is the one link a customer
# with no Zybrannox account is meant to open directly (from WhatsApp,
# say). Security here is the token's own unguessable length (see
# repository.py's secrets.token_urlsafe(32)), not a login wall.
@router.get("/public/documents/{token}")
def get_shared_document(token: str, db: Session = Depends(get_db)):
    path, display_name = service_get_document_path(db, token)
    return FileResponse(
        path,
        media_type="application/pdf",
        # inline, not attachment - opening the link should preview the PDF
        # right in the browser/WhatsApp's in-app viewer, not force a blind
        # download prompt before the recipient has even seen what it is.
        headers={"Content-Disposition": f'inline; filename="{display_name}"'},
    )
