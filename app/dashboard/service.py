from datetime import datetime

from sqlalchemy.orm import Session

from app.invoices.repository import get_latest_invoice_for_project

from .repository import (
    get_attention_projects,
    get_priority_breakdown,
    get_project_status_breakdown,
    get_recent_deliveries,
    get_recent_invoices,
    get_revenue_trend,
    get_stats,
    get_top_customers,
)


def service_get_summary(db: Session, granularity: str = "month") -> dict:
    recent_invoices = get_recent_invoices(db)
    attention_projects = get_attention_projects(db)
    recent_deliveries = get_recent_deliveries(db)

    return {
        "stats": get_stats(db),
        "project_status_breakdown": get_project_status_breakdown(db),
        "priority_breakdown": get_priority_breakdown(db),
        "revenue_trend": get_revenue_trend(db, granularity=granularity),
        "top_customers": get_top_customers(db),
        "recent_invoices": [
            {
                "id": inv.id,
                "invoice_number": inv.invoice_number,
                "customer_name": inv.customer_name,
                "project_type": inv.project_type,
                "amount": inv.amount,
                "status": inv.status,
                "created_at": inv.created_at,
            }
            for inv in recent_invoices
        ],
        "attention_projects": [
            {
                "id": p.id,
                "project_type": p.project_type,
                "customer_name": p.customer_name,
                "priority": p.priority,
                "print_status": p.print_status,
                "delivery_date": p.delivery_date,
                "is_overdue": bool(p.delivery_date and p.delivery_date < datetime.utcnow()),
                # A credit-delivered project can only have reached this
                # list via the credit-unpaid branch of get_attention_
                # projects (that branch requires delivered_at to be set,
                # which is mutually exclusive with the "not yet delivered"
                # branch) - so the flag alone is enough here, no need to
                # re-check the invoice again.
                "is_credit_unpaid": bool(p.delivered_on_credit),
            }
            for p in attention_projects
        ],
        "recent_deliveries": _serialize_recent_deliveries(db, recent_deliveries),
    }


def _serialize_recent_deliveries(db: Session, projects) -> list[dict]:
    result = []
    for p in projects:
        latest_invoice = get_latest_invoice_for_project(db, p.id)
        result.append(
            {
                "id": p.id,
                "project_type": p.project_type,
                "customer_name": p.customer_name,
                "delivered_at": p.delivered_at,
                "delivered_by": p.delivered_by,
                "delivered_on_credit": p.delivered_on_credit,
                "payment_status": latest_invoice.status if latest_invoice else None,
            }
        )
    return result
