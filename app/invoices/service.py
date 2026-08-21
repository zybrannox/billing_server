import math
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.entities.project import Project
from app.entities.customer import Customer
from .repository import (
    create_invoice,
    get_invoice,
    get_all_invoices,
    update_invoice,
    delete_invoice
)
from .model import InvoiceCreate, InvoiceUpdate, InvoiceListResponse

def service_create(db: Session, payload: InvoiceCreate):
    return create_invoice(db, payload)

def service_list(db: Session, page: int = 1, page_size: int = 20) -> InvoiceListResponse:
    items, total = get_all_invoices(db, page=page, page_size=page_size)
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


def service_get_details(db: Session, invoice_id: int):
    invoice = get_invoice(db, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    project = db.query(Project).filter(Project.id == invoice.project_id).first()
    customer = None
    if project and project.customer_id:
        customer = db.query(Customer).filter(Customer.id == project.customer_id).first()

    return {
        "id": invoice.id,
        "project_id": invoice.project_id,
        "invoice_number": invoice.invoice_number,
        "amount": invoice.amount,
        "status": invoice.status,
        "created_at": invoice.created_at,
        "due_date": invoice.due_date,
        "project": project,
        "customer": customer,
    }

def service_update(db: Session, invoice_id: int, payload: InvoiceUpdate):
    invoice = update_invoice(db, invoice_id, payload)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice

def service_delete(db: Session, invoice_id: int):
    success = delete_invoice(db, invoice_id)
    if not success:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return {"message": "Invoice deleted successfully"}
