"""Payments recorded on a customer and split across their invoices.

Admin-only, like the customer profile they're made from: this moves money
across several invoices at once, and can reverse it.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.audit import record_audit
from app.auth.dependencies import require_admin
from app.database import get_db
from app.entities import Customer, CustomerPayment
from app.errors import NotFound

from . import service
from .model import ApplyCredit, CustomerPaymentCreate, CustomerPaymentList, CustomerPaymentRead, OpenInvoice

router = APIRouter(tags=["Customer payments"])


def _customer(db: Session, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise NotFound("Customer")
    return customer


def _read(db: Session, payment: CustomerPayment) -> dict:
    return service.describe(db, [payment])[0]


def _audit(db: Session, username: str, action: str, payment: dict, extra: dict | None = None) -> None:
    record_audit(db, username, action, "customer", payment["customer_id"], {
        "label": f"Payment {service.rupees(payment['amount'])}",
        "amount": payment["amount"],
        "payment_method": payment["payment_method"],
        "reference": payment["payment_reference"],
        "applied_to": [f"{a['invoice_number']} {service.rupees(a['amount'])}" for a in payment["applied_to"]],
        "unused": payment["unused"],
        **(extra or {}),
    })


@router.get("/customers/{customer_id}/open-invoices", response_model=list[OpenInvoice])
def list_open_invoices(customer_id: int, db: Session = Depends(get_db), _admin: dict = Depends(require_admin)):
    _customer(db, customer_id)
    return [
        {
            "id": i.id,
            "invoice_number": i.invoice_number,
            "created_at": i.created_at,
            "due_date": i.due_date,
            "job": i.project.project_type if i.project else None,
            "amount": i.amount,
            "balance_due": i.balance_due,
        }
        for i in service.open_invoices(db, customer_id)
    ]


@router.get("/customers/{customer_id}/payments", response_model=CustomerPaymentList)
def list_customer_payments(customer_id: int, db: Session = Depends(get_db), _admin: dict = Depends(require_admin)):
    _customer(db, customer_id)
    items = service.describe(db, service.list_payments(db, customer_id))
    return {"items": items, "credit": round(sum(p["unused"] for p in items), 2)}


@router.post("/customers/{customer_id}/payments", response_model=CustomerPaymentRead)
def receive_payment(
    customer_id: int, payload: CustomerPaymentCreate, db: Session = Depends(get_db), _admin: dict = Depends(require_admin)
):
    payment = _read(db, service.record(db, customer_id, payload, _admin["username"]))
    _audit(db, _admin["username"], "customer.payment", payment)
    return payment


@router.post("/customer-payments/{payment_id}/apply", response_model=CustomerPaymentRead)
def apply_credit(payment_id: int, payload: ApplyCredit, db: Session = Depends(get_db), _admin: dict = Depends(require_admin)):
    payment = _read(db, service.apply_credit(db, payment_id, payload.allocations, _admin["username"]))
    _audit(db, _admin["username"], "customer.payment_apply", payment)
    return payment


@router.delete("/customer-payments/{payment_id}")
def delete_payment(payment_id: int, db: Session = Depends(get_db), _admin: dict = Depends(require_admin)):
    return service.delete(db, payment_id, _admin["username"])
