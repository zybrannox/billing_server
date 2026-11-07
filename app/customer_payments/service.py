"""A customer's payments: one sum, split across their unpaid invoices.

Rules, all enforced here rather than trusted from the screen:
- a share only goes to one of *this* customer's invoices that is still pending,
  and never more than that invoice's balance;
- the shares never add up to more than the payment (what's left is credit);
- recording a payment and splitting it happen in one transaction, so an
  invoice is never left half-updated;
- deleting a payment first reverses every share it made (paid invoices go back
  to pending), then moves it to the Bin. Restoring it brings it back as credit.

Each share is an ordinary InvoicePayment row (see entities/customer_payment.py),
so every screen that reads an invoice's balance or history needs no change.
"""
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Iterable, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.bin.service import BinEntry, move_to_bin
from app.datetime_utils import to_naive_utc, utcnow
from app.entities import Customer, CustomerPayment, Invoice, InvoicePayment
from app.entities.project import Project
from app.errors import BadRequest, NotFound

from .model import Allocation, CustomerPaymentCreate


def _r(value: float) -> float:
    return round(value + 0.0, 2)


def rupees(value: float) -> str:
    return f"₹{value:,.2f}".replace(".00", "")


# ---------------------------------------------------------------- reading

def open_invoices(db: Session, customer_id: int) -> list[Invoice]:
    """This customer's unpaid invoices, oldest first: the order a payment fills them."""
    rows = (
        db.query(Invoice)
        .join(Project, Invoice.project_id == Project.id)
        .options(joinedload(Invoice.project))
        .filter(Project.customer_id == customer_id, Invoice.status == "pending")
        .order_by(Invoice.created_at.asc(), Invoice.id.asc())
        .all()
    )
    return [i for i in rows if i.balance_due > 0]


def _applied(db: Session, payment_ids: Iterable[int]) -> dict[int, dict[int, float]]:
    """payment id -> {invoice id: net amount it put on that invoice}."""
    ids = list(payment_ids)
    out: dict[int, dict[int, float]] = defaultdict(dict)
    if not ids:
        return out
    rows = (
        db.query(InvoicePayment.customer_payment_id, InvoicePayment.invoice_id, func.sum(InvoicePayment.amount))
        .filter(InvoicePayment.customer_payment_id.in_(ids))
        .group_by(InvoicePayment.customer_payment_id, InvoicePayment.invoice_id)
        .all()
    )
    for payment_id, invoice_id, total in rows:
        out[payment_id][invoice_id] = _r(total or 0)
    return out


def unused_of(db: Session, payment: CustomerPayment) -> float:
    used = sum(_applied(db, [payment.id]).get(payment.id, {}).values())
    # Never below zero: a share can come back when a deleted invoice is restored
    # after its money was spent elsewhere. Showing negative credit would only confuse.
    return max(0.0, _r(payment.amount - used))


def describe(db: Session, payments: list[CustomerPayment]) -> list[dict]:
    applied = _applied(db, [p.id for p in payments])
    invoice_ids = {i for shares in applied.values() for i in shares}
    numbers = dict(db.query(Invoice.id, Invoice.invoice_number).filter(Invoice.id.in_(invoice_ids)).all()) if invoice_ids else {}
    result = []
    for p in payments:
        shares = applied.get(p.id, {})
        result.append({
            "id": p.id,
            "customer_id": p.customer_id,
            "amount": p.amount,
            "payment_method": p.payment_method,
            "payment_reference": p.payment_reference,
            "note": p.note,
            "received_at": p.received_at,
            "recorded_by": p.recorded_by,
            "created_at": p.created_at,
            "applied_to": [
                {"invoice_id": i, "invoice_number": numbers.get(i), "amount": amt}
                for i, amt in sorted(shares.items())
                if amt > 0
            ],
            "unused": max(0.0, _r(p.amount - sum(shares.values()))),
        })
    return result


def list_payments(db: Session, customer_id: int, since: Optional[datetime] = None, before: Optional[datetime] = None) -> list[CustomerPayment]:
    query = db.query(CustomerPayment).filter(CustomerPayment.customer_id == customer_id)
    if since:
        query = query.filter(CustomerPayment.received_at >= since)
    if before:
        query = query.filter(CustomerPayment.received_at < before)
    return query.order_by(CustomerPayment.received_at.desc(), CustomerPayment.id.desc()).all()


def credit_of(db: Session, customer_id: int) -> float:
    return _r(sum(d["unused"] for d in describe(db, list_payments(db, customer_id))))


# ---------------------------------------------------------------- writing

def _apply(db: Session, payment: CustomerPayment, allocations: list[Allocation], username: str, at: datetime) -> None:
    """Puts shares of `payment` on invoices. Caller commits."""
    if not allocations:
        return
    total = _r(sum(a.amount for a in allocations))
    available = unused_of(db, payment) if payment.id else payment.amount
    if total > _r(available):
        raise BadRequest(f"That's {rupees(total)} across the invoices, but only {rupees(available)} of this payment is left.")

    ids = [a.invoice_id for a in allocations]
    # Locked until commit, so two people paying the same invoice at once can't
    # both see the old balance (no-op on SQLite, real on Postgres).
    invoices = {
        i.id: i
        for i in db.query(Invoice)
        .join(Project, Invoice.project_id == Project.id)
        .filter(Invoice.id.in_(ids), Project.customer_id == payment.customer_id)
        .with_for_update(of=Invoice)
        .all()
    }
    for allocation in allocations:
        invoice = invoices.get(allocation.invoice_id)
        if invoice is None:
            raise BadRequest("One of those invoices isn't this customer's.")
        label = invoice.invoice_number or f"Invoice #{invoice.id}"
        if invoice.status != "pending":
            raise BadRequest(f"{label} is already {invoice.status}.")
        amount = _r(allocation.amount)
        if amount > invoice.balance_due:
            raise BadRequest(f"{label} only has {rupees(invoice.balance_due)} left to pay.")

        new_advance = _r((invoice.advance_amount or 0) + amount)
        if new_advance >= _r(invoice.amount):
            new_advance = invoice.amount
            invoice.status = "paid"
            invoice.paid_at = at
        invoice.advance_amount = new_advance
        invoice.payment_method = payment.payment_method
        invoice.payment_reference = payment.payment_reference
        db.add(InvoicePayment(
            invoice_id=invoice.id,
            amount=amount,
            payment_method=payment.payment_method,
            payment_reference=payment.payment_reference,
            paid_at=at,
            recorded_by=username,
            customer_payment_id=payment.id,
        ))


def record(db: Session, customer_id: int, payload: CustomerPaymentCreate, username: str) -> CustomerPayment:
    if db.get(Customer, customer_id) is None:
        raise NotFound("Customer")
    now = utcnow()
    received = to_naive_utc(payload.received_at) if payload.received_at else now
    # A little slack for a phone whose clock runs ahead.
    if received > now + timedelta(days=1):
        raise BadRequest("The payment date can't be in the future.")

    try:
        payment = CustomerPayment(
            customer_id=customer_id,
            amount=_r(payload.amount),
            payment_method=payload.payment_method,
            payment_reference=(payload.payment_reference or "").strip() or None,
            note=(payload.note or "").strip() or None,
            received_at=received,
            recorded_by=username,
            created_at=now,
        )
        db.add(payment)
        db.flush()
        _apply(db, payment, payload.allocations, username, received)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(payment)
    return payment


def _locked_payment(db: Session, payment_id: int) -> CustomerPayment:
    payment = db.query(CustomerPayment).filter(CustomerPayment.id == payment_id).with_for_update().first()
    if payment is None:
        raise NotFound("Payment")
    return payment


def apply_credit(db: Session, payment_id: int, allocations: list[Allocation], username: str) -> CustomerPayment:
    try:
        payment = _locked_payment(db, payment_id)
        _apply(db, payment, allocations, username, utcnow())
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(payment)
    return payment


def _reverse(db: Session, invoice: Invoice, payment_id: int, amount: float, username: str, method: Optional[str]) -> None:
    """Takes `amount` of a customer payment back off an invoice. Caller commits."""
    invoice.advance_amount = max(0.0, _r((invoice.advance_amount or 0) - amount))
    if invoice.status == "paid" and invoice.advance_amount < _r(invoice.amount):
        invoice.status = "pending"
        invoice.paid_at = None
    db.add(InvoicePayment(
        invoice_id=invoice.id,
        amount=-amount,
        payment_method=method,
        payment_reference="Reversed",
        paid_at=utcnow(),
        recorded_by=username,
        customer_payment_id=payment_id,
    ))


def delete(db: Session, payment_id: int, username: str) -> dict:
    payment = _locked_payment(db, payment_id)
    shares = {i: amt for i, amt in _applied(db, [payment.id]).get(payment.id, {}).items() if amt > 0}
    invoices = db.query(Invoice).filter(Invoice.id.in_(list(shares))).with_for_update().all() if shares else []
    reversed_on = []
    try:
        for invoice in invoices:
            _reverse(db, invoice, payment.id, shares[invoice.id], username, payment.payment_method)
            reversed_on.append(invoice.invoice_number or f"Invoice #{invoice.id}")
        db.flush()
    except Exception:
        db.rollback()
        raise
    customer = db.get(Customer, payment.customer_id)
    name = f"{customer.first_name} {customer.last_name}".strip() if customer else None
    # Commits the reversals and the delete together.
    move_to_bin(
        db,
        [BinEntry("customer_payment", payment, f"Payment {rupees(payment.amount)} · {payment.payment_method}", name)],
        username,
    )
    return {"message": "Payment moved to the bin", "reversed_on": reversed_on}


def release_from_cancelled(db: Session, invoice: Invoice, username: str) -> None:
    """A cancelled invoice was never owed, so whatever customer payments put on
    it goes back to the customer as credit. Payments taken on the invoice itself
    are left as they were. Caller commits."""
    shares = (
        db.query(InvoicePayment.customer_payment_id, func.sum(InvoicePayment.amount))
        .filter(InvoicePayment.invoice_id == invoice.id, InvoicePayment.customer_payment_id.isnot(None))
        .group_by(InvoicePayment.customer_payment_id)
        .all()
    )
    for payment_id, total in shares:
        amount = _r(total or 0)
        if amount > 0:
            _reverse(db, invoice, payment_id, amount, username, invoice.payment_method)
