from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.dependencies import require_admin, get_current_user
from .model import (
    InvoiceCreate,
    InvoiceRead,
    InvoiceUpdate,
    InvoiceDetailRead,
    InvoiceListResponse,
    InvoicePreviewRead,
    ProjectPaymentStatus,
    MarkInvoicePaidRequest,
)
from .service import (
    service_create,
    service_list,
    service_get,
    service_get_details,
    service_get_invoice_preview,
    service_get_project_payment_status,
    service_get_latest_invoice_for_project,
    service_update,
    service_mark_paid,
    service_delete
)

router = APIRouter(prefix="/invoices", tags=["Invoices"])

# Generating an invoice happens as part of an employee finishing their own
# assigned work (see GenerateInvoice.tsx, opened from "Design completed" -
# any role can trigger that), so create/preview/details are open to any
# authenticated user, not just admins. The financial-oversight surface -
# the full list across every project (GET /), and editing/deleting an
# existing invoice's status - stays admin-only.

@router.post("/", response_model=InvoiceRead)
def create(payload: InvoiceCreate, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    return service_create(db, payload)

@router.get("/", response_model=InvoiceListResponse)
def list_invoices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    return service_list(db, page=page, page_size=page_size, search=search)

# Two path segments after /invoices/ (preview/{project_id}) so this never
# collides with GET /invoices/{invoice_id} below, which only matches one.
# Used by the Create Invoice screen to show the project/customer details
# before any Invoice row exists yet.
@router.get("/preview/{project_id}", response_model=InvoicePreviewRead)
def get_invoice_preview(project_id: int, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    return service_get_invoice_preview(db, project_id)

# Gates the "Deliver" action (see Projects.tsx's onMarkDelivered) on the
# project's most recent invoice actually being paid - open to any
# authenticated user for the same reason preview/create are: any role can
# be the one delivering their own assigned work, not just admins.
@router.get("/payment-status/{project_id}", response_model=ProjectPaymentStatus)
def get_project_payment_status(project_id: int, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    return service_get_project_payment_status(db, project_id)

# Three path segments (project/{project_id}/latest) - never collides with
# the one- and two-segment routes above/below. Powers the "Deliver" dialog's
# full order/payment breakdown (see Projects.tsx's DeliveryCheck); 404 when
# the project has no invoice yet, which the dialog renders as its own
# "not invoiced" empty state rather than treating as an error.
@router.get("/project/{project_id}/latest", response_model=InvoiceDetailRead)
def get_latest_invoice_for_project(project_id: int, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    return service_get_latest_invoice_for_project(db, project_id)

@router.get("/{invoice_id}/details", response_model=InvoiceDetailRead)
def get_invoice_details(invoice_id: int, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    return service_get_details(db, invoice_id)

@router.get("/{invoice_id}", response_model=InvoiceRead)
def get_invoice(invoice_id: int, db: Session = Depends(get_db), _admin: dict = Depends(require_admin)):
    return service_get(db, invoice_id)

@router.patch("/{invoice_id}", response_model=InvoiceRead)
def update_invoice(invoice_id: int, payload: InvoiceUpdate, db: Session = Depends(get_db), _admin: dict = Depends(require_admin)):
    return service_update(db, invoice_id, payload)

# Open to any authenticated user, unlike the generic update above - same
# reasoning as create/preview/deliver: marking your own delivered work as
# paid is part of finishing it, not a financial-oversight action. Its
# request body (MarkInvoicePaidRequest) is deliberately narrower than
# InvoiceUpdate so this can't become a route to the discount/amount edits
# that stay admin-only.
@router.patch("/{invoice_id}/mark-paid", response_model=InvoiceRead)
def mark_invoice_paid(
    invoice_id: int,
    payload: MarkInvoicePaidRequest,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    return service_mark_paid(db, invoice_id, payload.payment_method, payload.payment_reference)

@router.delete("/{invoice_id}")
def delete_invoice(invoice_id: int, db: Session = Depends(get_db), _admin: dict = Depends(require_admin)):
    return service_delete(db, invoice_id)
