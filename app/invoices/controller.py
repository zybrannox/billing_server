from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from .model import InvoiceCreate, InvoiceRead, InvoiceUpdate
from .service import (
    service_create,
    service_list,
    service_get,
    service_update,
    service_delete
)

router = APIRouter(prefix="/invoices", tags=["Invoices"])

@router.post("/", response_model=InvoiceRead)
def create(payload: InvoiceCreate, db: Session = Depends(get_db)):
    return service_create(db, payload)

@router.get("/", response_model=list[InvoiceRead])
def list_invoices(db: Session = Depends(get_db)):
    return service_list(db)

@router.get("/{invoice_id}", response_model=InvoiceRead)
def get_invoice(invoice_id: int, db: Session = Depends(get_db)):
    return service_get(db, invoice_id)

@router.patch("/{invoice_id}", response_model=InvoiceRead)
def update_invoice(invoice_id: int, payload: InvoiceUpdate, db: Session = Depends(get_db)):
    return service_update(db, invoice_id, payload)

@router.delete("/{invoice_id}")
def delete_invoice(invoice_id: int, db: Session = Depends(get_db)):
    return service_delete(db, invoice_id)
