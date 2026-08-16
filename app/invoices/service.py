from sqlalchemy.orm import Session
from fastapi import HTTPException
from .repository import (
    create_invoice,
    get_invoice,
    get_all_invoices,
    update_invoice,
    delete_invoice
)
from .model import InvoiceCreate, InvoiceUpdate

def service_create(db: Session, payload: InvoiceCreate):
    return create_invoice(db, payload)

def service_list(db: Session):
    return get_all_invoices(db)

def service_get(db: Session, invoice_id: int):
    invoice = get_invoice(db, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice

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
