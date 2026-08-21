from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.dependencies import require_admin
from .model import InvoiceCreate, InvoiceRead, InvoiceUpdate, InvoiceDetailRead, InvoiceListResponse
from .service import (
    service_create,
    service_list,
    service_get,
    service_get_details,
    service_update,
    service_delete
)

router = APIRouter(prefix="/invoices", tags=["Invoices"])

# Billing/invoices are admin-only in the UI (/admin/billing) and expose
# financial data - every endpoint here requires admin, not just login.

@router.post("/", response_model=InvoiceRead)
def create(payload: InvoiceCreate, db: Session = Depends(get_db), _admin: dict = Depends(require_admin)):
    return service_create(db, payload)

@router.get("/", response_model=InvoiceListResponse)
def list_invoices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    return service_list(db, page=page, page_size=page_size)

@router.get("/{invoice_id}/details", response_model=InvoiceDetailRead)
def get_invoice_details(invoice_id: int, db: Session = Depends(get_db), _admin: dict = Depends(require_admin)):
    return service_get_details(db, invoice_id)

@router.get("/{invoice_id}", response_model=InvoiceRead)
def get_invoice(invoice_id: int, db: Session = Depends(get_db), _admin: dict = Depends(require_admin)):
    return service_get(db, invoice_id)

@router.patch("/{invoice_id}", response_model=InvoiceRead)
def update_invoice(invoice_id: int, payload: InvoiceUpdate, db: Session = Depends(get_db), _admin: dict = Depends(require_admin)):
    return service_update(db, invoice_id, payload)

@router.delete("/{invoice_id}")
def delete_invoice(invoice_id: int, db: Session = Depends(get_db), _admin: dict = Depends(require_admin)):
    return service_delete(db, invoice_id)
