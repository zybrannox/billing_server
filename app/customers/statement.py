"""A customer's statement: their bills over a period, what's paid and what's owed."""
from datetime import datetime
from typing import List, Literal, Optional

from sqlalchemy.orm import Session, joinedload

from app.customers.billing import customer_bill_to
from app.datetime_utils import OptionalUTCDateTime, UTCDateTime, to_naive_utc, utcnow
from app.entities import Customer, Invoice
from app.entities.project import Project
from app.invoices.model import CustomerSummary
from app.response_model import ResponseModel


class StatementRow(ResponseModel):
    invoice_id: int
    invoice_number: Optional[str]
    date: UTCDateTime
    due_date: OptionalUTCDateTime
    job: Optional[str]
    amount: float
    paid: float
    balance: float
    status: Literal["pending", "paid"]


class CustomerStatement(ResponseModel):
    customer: CustomerSummary
    date_from: OptionalUTCDateTime
    date_to: OptionalUTCDateTime
    generated_at: UTCDateTime
    rows: List[StatementRow]
    total_billed: float
    total_paid: float
    total_balance: float
    # Everything they owe, whatever the period: what a statement is usually for.
    total_outstanding: float


def _paid(invoice: Invoice) -> float:
    # Same rule as the customer profile's Outstanding: a paid invoice is settled in
    # full, a pending one owes its balance.
    return invoice.amount if invoice.status == "paid" else round(invoice.amount - invoice.balance_due, 2)


def build_statement(
    db: Session, customer: Customer, date_from: Optional[datetime], date_to: Optional[datetime]
) -> dict:
    # Cancelled invoices were never owed, so they don't belong on a statement.
    invoices = (
        db.query(Invoice)
        .join(Project, Invoice.project_id == Project.id)
        .options(joinedload(Invoice.project))
        .filter(Project.customer_id == customer.id, Invoice.status.in_(["pending", "paid"]))
    )
    in_period = invoices
    if date_from:
        in_period = in_period.filter(Invoice.created_at >= to_naive_utc(date_from))
    if date_to:
        in_period = in_period.filter(Invoice.created_at < to_naive_utc(date_to))

    rows = [
        {
            "invoice_id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "date": invoice.created_at,
            "due_date": invoice.due_date,
            "job": invoice.project.project_type if invoice.project else None,
            "amount": invoice.amount,
            "paid": _paid(invoice),
            "balance": round(invoice.amount - _paid(invoice), 2),
            "status": invoice.status,
        }
        for invoice in in_period.order_by(Invoice.created_at.asc(), Invoice.id.asc()).all()
    ]
    total_outstanding = sum(invoice.balance_due for invoice in invoices.filter(Invoice.status == "pending").all())

    return {
        "customer": customer_bill_to(db, customer),
        "date_from": date_from,
        "date_to": date_to,
        "generated_at": utcnow(),
        "rows": rows,
        "total_billed": round(sum(r["amount"] for r in rows), 2),
        "total_paid": round(sum(r["paid"] for r in rows), 2),
        "total_balance": round(sum(r["balance"] for r in rows), 2),
        "total_outstanding": round(total_outstanding, 2),
    }
