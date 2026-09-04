import math
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.entities.project import Project
from .calculations import compute_invoice_total
from .repository import (
    create_invoice,
    get_invoice,
    get_all_invoices,
    get_latest_invoice_for_project,
    get_project_with_customer,
    update_invoice,
    delete_invoice
)
from .model import InvoiceCreate, InvoiceUpdate, InvoiceListResponse

def service_create(db: Session, payload: InvoiceCreate):
    # FK alone would turn a bad project_id into a raw 500 (constraint
    # violation) - check up front so a stale/mistyped project id in the
    # request surfaces as an ordinary 404 instead.
    project_exists = db.query(Project.id).filter(Project.id == payload.project_id).first()
    if not project_exists:
        raise HTTPException(status_code=404, detail="Project not found")

    subtotal = compute_invoice_total(payload.items)

    if payload.discount_amount > subtotal:
        raise HTTPException(
            status_code=400,
            detail="Discount can't exceed the invoice subtotal",
        )
    total_after_discount = round(subtotal - payload.discount_amount, 2)

    if payload.advance_amount > 0:
        if not payload.payment_method:
            raise HTTPException(
                status_code=400,
                detail="Payment method is required when recording an advance payment",
            )
        # Checked against what's actually owed after the discount, not the
        # raw subtotal - an advance can't exceed the real total.
        if payload.advance_amount > total_after_discount:
            raise HTTPException(
                status_code=400,
                detail="Advance amount can't exceed the invoice total",
            )

    return create_invoice(db, payload)

def service_list(db: Session, page: int = 1, page_size: int = 20, search: str | None = None) -> InvoiceListResponse:
    items, total = get_all_invoices(db, page=page, page_size=page_size, search=search)
    total_pages = math.ceil(total / page_size) if page_size else 0
    return InvoiceListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )

def service_get(db: Session, invoice_id: int):
    invoice = get_invoice(db, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


def _invoice_detail_dict(db: Session, invoice):
    """Shared by service_get_details (looked up by invoice id) and
    service_get_latest_invoice_for_project (looked up by project id) -
    both need the exact same shape, just found a different way."""
    project, customer = get_project_with_customer(db, invoice.project_id)
    return {
        "id": invoice.id,
        "project_id": invoice.project_id,
        "invoice_number": invoice.invoice_number,
        "subtotal": invoice.subtotal,
        "discount_amount": invoice.discount_amount,
        "amount": invoice.amount,
        "status": invoice.status,
        "created_at": invoice.created_at,
        "due_date": invoice.due_date,
        "advance_amount": invoice.advance_amount,
        "payment_method": invoice.payment_method,
        "payment_reference": invoice.payment_reference,
        "balance_due": invoice.balance_due,
        "customer_name": f"{customer.first_name} {customer.last_name}" if customer else None,
        "project_type": project.project_type if project else None,
        "project": project,
        "customer": customer,
        "items": invoice.items,
    }


def service_get_details(db: Session, invoice_id: int):
    invoice = get_invoice(db, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return _invoice_detail_dict(db, invoice)


def service_get_invoice_preview(db: Session, project_id: int):
    project, customer = get_project_with_customer(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"project": project, "customer": customer}


def service_get_project_payment_status(db: Session, project_id: int):
    invoice = get_latest_invoice_for_project(db, project_id)
    if not invoice:
        return {"is_paid": False, "invoice_number": None, "invoice_status": None, "balance_due": None}
    return {
        "is_paid": invoice.status == "paid",
        "invoice_number": invoice.invoice_number,
        "invoice_status": invoice.status,
        "balance_due": invoice.balance_due,
    }


def service_get_latest_invoice_for_project(db: Session, project_id: int):
    """Powers the "Deliver" dialog's full order/payment breakdown (see
    Projects.tsx's DeliveryCheck) - the same rich detail shape as
    service_get_details, just found by project instead of by invoice id,
    since that dialog only knows which project it's delivering."""
    invoice = get_latest_invoice_for_project(db, project_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="No invoice found for this project")
    return _invoice_detail_dict(db, invoice)

VALID_STATUSES = {"pending", "paid", "cancelled"}

def service_update(db: Session, invoice_id: int, payload: InvoiceUpdate):
    invoice = get_invoice(db, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # "paid" and "cancelled" are terminal - once there, neither Mark Paid
    # nor Cancel should be able to move it anywhere else. The frontend
    # already disables both buttons once an invoice leaves "pending" (see
    # ui/Actions.tsx), but that's just UI - a stale page, a replayed
    # request, or a client bug could still fire the PATCH, so the actual
    # rule has to live here too, not only in what buttons happen to be
    # clickable.
    if payload.status is not None and payload.status != invoice.status:
        if invoice.status != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"This invoice is already {invoice.status} - its status can't be changed.",
            )
        if payload.status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"Unknown status '{payload.status}'")

    # Discount can only move while the invoice is still pending - once
    # it's paid or cancelled, changing it would silently disagree with
    # money that's already been reconciled. `amount` (subtotal minus
    # discount - see Invoice.balance_due) isn't a real editable field on
    # its own; it has to be recomputed together with discount_amount right
    # here; update_invoice's generic setattr loop would otherwise apply
    # the new discount_amount but leave the old, now-wrong amount in place.
    if payload.discount_amount is not None and payload.discount_amount != invoice.discount_amount:
        if invoice.status != "pending":
            raise HTTPException(
                status_code=400,
                detail=f"This invoice is already {invoice.status} - its discount can't be changed.",
            )
        if payload.discount_amount > invoice.subtotal:
            raise HTTPException(
                status_code=400,
                detail="Discount can't exceed the invoice subtotal",
            )
        new_amount = round(invoice.subtotal - payload.discount_amount, 2)
        if invoice.advance_amount > new_amount:
            raise HTTPException(
                status_code=400,
                detail="Discount would bring the total below the advance already recorded",
            )
        payload = payload.model_copy(update={"amount": new_amount})

    updated = update_invoice(db, invoice_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return updated

def service_delete(db: Session, invoice_id: int):
    success = delete_invoice(db, invoice_id)
    if not success:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {"message": "Invoice deleted successfully"}
