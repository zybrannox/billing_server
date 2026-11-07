from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.audit import record_audit
from app.auth.permissions import INVOICE_EDIT, require_permission
from app.entities import Invoice
from app.errors import NotFound
from app.auth.dependencies import require_admin, get_current_user
from .model import InvoiceSummary, InvoiceView
from .repository import get_invoice_summary
from .model import (
    InvoiceCreate,
    InvoiceRead,
    InvoiceUpdate,
    InvoiceDetailRead,
    InvoiceListResponse,
    InvoicePreviewRead,
    ProjectPaymentStatus,
    MarkInvoicePaidRequest,
    RecordPaymentRequest,
    InvoicePaymentRead,
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
    service_record_payment,
    service_get_payments,
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
def create(payload: InvoiceCreate, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    return service_create(db, payload, current_user["username"])

@router.get("/", response_model=InvoiceListResponse)
def list_invoices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    customer_id: int | None = Query(None),
    company_id: int | None = Query(None),
    view: InvoiceView | None = Query(None),
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    return service_list(
        db, page=page, page_size=page_size, search=search, customer_id=customer_id, company_id=company_id, view=view
    )

# One path segment, so it has to stay above GET /{invoice_id} below. The offset
# is the browser's, so "due today" means today where the shop is.
@router.get("/summary", response_model=InvoiceSummary)
def get_summary(
    tz_offset_minutes: int = Query(330, ge=-840, le=840),
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    return get_invoice_summary(db, tz_offset_minutes)

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

@router.get("/{invoice_id}/payments", response_model=list[InvoicePaymentRead])
def get_invoice_payments(invoice_id: int, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    return service_get_payments(db, invoice_id)

@router.get("/{invoice_id}", response_model=InvoiceRead)
def get_invoice(invoice_id: int, db: Session = Depends(get_db), _admin: dict = Depends(require_admin)):
    return service_get(db, invoice_id)

@router.patch("/{invoice_id}", response_model=InvoiceRead)
def update_invoice(invoice_id: int, payload: InvoiceUpdate, db: Session = Depends(get_db), _admin: dict = Depends(require_permission(INVOICE_EDIT))):
    # Edit access is for correcting an invoice's details. Cancelling one (a status
    # change) stays with admins.
    if "status" in payload.model_fields_set and _admin.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only an admin can cancel an invoice.")
    before_status = None
    if "status" in payload.model_fields_set:
        current = db.get(Invoice, invoice_id)
        if not current:
            raise NotFound("Invoice")
        before_status = current.status
    invoice = service_update(db, invoice_id, payload, _admin["username"])
    # Edits to the invoice's details are logged automatically (app/audit/tracker.py);
    # its status is left to this, so cancelling reads as exactly that.
    if before_status is not None and invoice.status != before_status:
        record_audit(
            db, _admin["username"], "invoice.cancel" if invoice.status == "cancelled" else "invoice.status", "invoice", invoice_id,
            {
                "label": invoice.invoice_number,
                "changes": [{"field": "status", "label": "Status", "from": before_status, "to": invoice.status}],
            },
        )
    return invoice

# Open to any authenticated user, unlike the generic update above - same
# reasoning as create/preview/deliver: marking your own delivered work as
# paid is part of finishing it, not a financial-oversight action. Its
# request body (MarkInvoicePaidRequest) is deliberately narrower than
# InvoiceUpdate so this can't become a route to the discount/amount edits
# that stay admin-only.
def _payment_state(db: Session, invoice_id: int) -> tuple:
    invoice = db.get(Invoice, invoice_id)
    return (invoice.advance_amount, invoice.status) if invoice else (None, None)


def _payment_changes(before: tuple, invoice) -> list[dict]:
    """What a payment moved, from what to what, for the activity log."""
    changes = []
    if before[0] != invoice.advance_amount:
        changes.append({"field": "advance_amount", "label": "Amount paid", "from": before[0], "to": invoice.advance_amount})
    if before[1] != invoice.status:
        changes.append({"field": "status", "label": "Status", "from": before[1], "to": invoice.status})
    return changes


@router.patch("/{invoice_id}/mark-paid", response_model=InvoiceRead)
def mark_invoice_paid(
    invoice_id: int,
    payload: MarkInvoicePaidRequest,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    before = _payment_state(db, invoice_id)
    invoice = service_mark_paid(
        db, invoice_id, payload.payment_method, payload.payment_reference, _user["username"]
    )
    record_audit(
        db, _user["username"], "invoice.mark_paid", "invoice", invoice_id,
        {
            "label": invoice.invoice_number,
            "payment_method": payload.payment_method,
            "reference": payload.payment_reference,
            "changes": _payment_changes(before, invoice),
        },
    )
    return invoice

@router.patch("/{invoice_id}/record-payment", response_model=InvoiceRead)
def record_invoice_payment(
    invoice_id: int,
    payload: RecordPaymentRequest,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    before = _payment_state(db, invoice_id)
    invoice = service_record_payment(
        db,
        invoice_id,
        payload.amount,
        payload.payment_method,
        payload.payment_reference,
        _user["username"],
    )
    record_audit(
        db, _user["username"], "invoice.payment", "invoice", invoice_id,
        {"label": invoice.invoice_number, "amount": payload.amount, "payment_method": payload.payment_method,
         "reference": payload.payment_reference, "changes": _payment_changes(before, invoice)},
    )
    return invoice

@router.delete("/{invoice_id}")
def delete_invoice(invoice_id: int, db: Session = Depends(get_db), _admin: dict = Depends(require_admin)):
    return service_delete(db, invoice_id, _admin["username"])
