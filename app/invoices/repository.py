from datetime import datetime
from sqlalchemy.orm import Session
from app.entities.invoice import Invoice
from .model import InvoiceCreate, InvoiceUpdate

def create_invoice(db: Session, invoice: InvoiceCreate):
    try:
        new_invoice = Invoice(**invoice.model_dump())
        db.add(new_invoice)
        db.commit()
        db.refresh(new_invoice)

        # invoice_number depends on the row's own id, so it can only be
        # generated after the insert - format: INV-<year>-<id, zero-padded>.
        year = (new_invoice.created_at or datetime.utcnow()).year
        new_invoice.invoice_number = f"INV-{year}-{new_invoice.id:05d}"
        db.commit()
        db.refresh(new_invoice)

        return new_invoice
    except Exception as e:
        db.rollback()
        print(f"ERROR creating invoice: {e}")
        raise e

def get_invoice(db: Session, invoice_id: int):
    return db.query(Invoice).filter(Invoice.id == invoice_id).first()

def get_all_invoices(db: Session, page: int = 1, page_size: int = 20):
    # Previously returned every invoice ever created, unpaginated - fine
    # with a handful of rows, but the response only grows over time (unlike
    # projects, invoices are never really "done" and cleared out), so this
    # was a slow-motion outage waiting for enough billing history to build
    # up. Matches the page/total_pages shape already used by
    # customers/projects.
    query = db.query(Invoice).order_by(Invoice.created_at.desc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return items, total

def update_invoice(db: Session, invoice_id: int, invoice: InvoiceUpdate):
    db_invoice = get_invoice(db, invoice_id)
    if not db_invoice:
        return None
    
    for key, value in invoice.model_dump(exclude_unset=True).items():
        setattr(db_invoice, key, value)
    
    db.commit()
    db.refresh(db_invoice)
    return db_invoice

def delete_invoice(db: Session, invoice_id: int):
    db_invoice = get_invoice(db, invoice_id)
    if not db_invoice:
        return False
    db.delete(db_invoice)
    db.commit()
    return True
