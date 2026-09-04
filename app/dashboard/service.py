from datetime import datetime

from sqlalchemy.orm import Session

from .repository import (
    get_attention_projects,
    get_priority_breakdown,
    get_project_status_breakdown,
    get_recent_invoices,
    get_revenue_trend,
    get_stats,
    get_top_customers,
)


def service_get_summary(db: Session, granularity: str = "month") -> dict:
    recent_invoices = get_recent_invoices(db)
    attention_projects = get_attention_projects(db)

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
            }
            for p in attention_projects
        ],
    }
