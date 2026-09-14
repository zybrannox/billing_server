from datetime import datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.entities.customer import Customer
from app.entities.invoice import Invoice
from app.entities.project import Project


def _latest_invoice_status_subquery():
    """A project can end up with more than one invoice over time (a
    cancelled one re-invoiced) - correlated so it always resolves to the
    most recently created one for whichever Project row it's compared
    against, matching get_latest_invoice_for_project's own definition of
    "latest" (see app/invoices/repository.py)."""
    return (
        select(Invoice.status)
        .where(Invoice.project_id == Project.id)
        .order_by(Invoice.created_at.desc())
        .limit(1)
        .correlate(Project)
        .scalar_subquery()
    )


def get_stats(db: Session) -> dict:
    total_customers = db.query(func.count(Customer.id)).scalar() or 0

    total_projects = db.query(func.count(Project.id)).scalar() or 0
    completed_projects = (
        db.query(func.count(Project.id)).filter(Project.print_status == "Completed").scalar() or 0
    )
    delivered_projects = (
        db.query(func.count(Project.id)).filter(Project.delivered_at.isnot(None)).scalar() or 0
    )

    total_revenue = (
        db.query(func.coalesce(func.sum(Invoice.amount), 0.0))
        .filter(Invoice.status == "paid")
        .scalar()
        or 0.0
    )

    now = datetime.utcnow()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # paid_at (when the money actually came in), not created_at (when the
    # invoice was raised) - an invoice created last month but only marked
    # paid today has to count as this month's revenue, not silently stay
    # parked in last month's bucket forever. Falls back to created_at for
    # invoices paid before this column existed (paid_at is nullable - see
    # entities/invoice.py).
    paid_date = func.coalesce(Invoice.paid_at, Invoice.created_at)
    revenue_this_month = (
        db.query(func.coalesce(func.sum(Invoice.amount), 0.0))
        .filter(Invoice.status == "paid", paid_date >= month_start)
        .scalar()
        or 0.0
    )

    # balance_due isn't a real column (it's amount - advance_amount,
    # floored at 0 - see Invoice.balance_due) so it can't be summed in
    # SQL directly. Pending invoices are a naturally small, bounded set
    # (the current unpaid backlog, not the whole invoice history), so
    # pulling just these two columns and reducing in Python is cheap and
    # exactly matches what the property itself computes - no drift risk
    # from re-deriving the formula in raw SQL.
    pending_amounts = (
        db.query(Invoice.amount, Invoice.advance_amount)
        .filter(Invoice.status == "pending")
        .all()
    )
    outstanding_balance = round(
        sum(max(0.0, amount - (advance or 0.0)) for amount, advance in pending_amounts), 2
    )
    pending_invoices = len(pending_amounts)

    overdue_invoices = (
        db.query(func.count(Invoice.id))
        .filter(
            Invoice.status == "pending",
            Invoice.due_date.isnot(None),
            Invoice.due_date < now,
        )
        .scalar()
        or 0
    )

    return {
        "total_customers": total_customers,
        "total_projects": total_projects,
        "active_projects": total_projects - completed_projects,
        "completed_projects": completed_projects,
        "delivered_projects": delivered_projects,
        "total_revenue": round(total_revenue, 2),
        "revenue_this_month": round(revenue_this_month, 2),
        "outstanding_balance": outstanding_balance,
        "pending_invoices": pending_invoices,
        "overdue_invoices": overdue_invoices,
    }


def get_project_status_breakdown(db: Session) -> list[dict]:
    rows = (
        db.query(Project.print_status, func.count(Project.id))
        .group_by(Project.print_status)
        .all()
    )
    return [{"label": status or "Unknown", "count": count} for status, count in rows]


def get_priority_breakdown(db: Session) -> list[dict]:
    rows = db.query(Project.priority, func.count(Project.id)).group_by(Project.priority).all()
    return [{"label": priority or "Unknown", "count": count} for priority, count in rows]


# Default number of buckets shown per granularity - chosen so each reads
# well on the chart (a 14-day sparkline, ~2 months of weeks, half a year of
# months, or a 5-year run) without the caller having to know sane defaults.
_TREND_PERIODS = {"day": 14, "week": 8, "month": 6, "year": 5}
_TREND_LABEL_FORMAT = {"day": "%b %d", "week": "%b %d", "month": "%b %Y", "year": "%Y"}
_TREND_KEY_FORMAT = {"day": "%Y-%m-%d", "week": "%Y-%m-%d", "month": "%Y-%m", "year": "%Y"}


def get_revenue_trend(db: Session, granularity: str = "month") -> list[dict]:
    periods = _TREND_PERIODS.get(granularity, _TREND_PERIODS["month"])
    key_fmt = _TREND_KEY_FORMAT.get(granularity, _TREND_KEY_FORMAT["month"])
    label_fmt = _TREND_LABEL_FORMAT.get(granularity, _TREND_LABEL_FORMAT["month"])
    now = datetime.utcnow()

    if granularity == "day":
        start = (now - timedelta(days=periods - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
        step = timedelta(days=1)
        bucket_keys = [start + step * i for i in range(periods)]
    elif granularity == "week":
        # date_trunc('week', ...) in Postgres truncates to the Monday of
        # that ISO week, so the generated keys below must match that.
        this_monday = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        start = this_monday - timedelta(weeks=periods - 1)
        step = timedelta(weeks=1)
        bucket_keys = [start + step * i for i in range(periods)]
    elif granularity == "year":
        start_year = now.year - (periods - 1)
        start = datetime(start_year, 1, 1)
        bucket_keys = [datetime(start_year + i, 1, 1) for i in range(periods)]
    else:  # "month" - first day of the month (periods - 1) months ago, so
        # e.g. periods=6 from August gives March 1st, covering six calendar
        # months including the current one. Plain month/year arithmetic
        # (no dateutil) avoids drift across months of different lengths.
        granularity = "month"
        total_months = now.year * 12 + (now.month - 1) - (periods - 1)
        start_year, start_month = divmod(total_months, 12)
        start = datetime(start_year, start_month + 1, 1)
        bucket_keys = []
        for i in range(periods):
            total = start_year * 12 + start_month + i
            y, m = divmod(total, 12)
            bucket_keys.append(datetime(y, m + 1, 1))

    # paid_at, not created_at - see get_stats' revenue_this_month for why
    # (same reasoning, same coalesce-to-created_at fallback).
    paid_date = func.coalesce(Invoice.paid_at, Invoice.created_at)
    bucket = func.date_trunc(granularity, paid_date)
    rows = (
        db.query(bucket.label("period"), func.coalesce(func.sum(Invoice.amount), 0.0))
        .filter(Invoice.status == "paid", paid_date >= start)
        .group_by(bucket)
        .order_by(bucket)
        .all()
    )
    # Every bucket in the window shows up even with zero revenue, so the
    # chart's x-axis doesn't silently skip a quiet day/week/month/year.
    by_bucket = {period.strftime(key_fmt): revenue for period, revenue in rows}
    return [
        {
            "period": key.strftime(label_fmt),
            "revenue": round(by_bucket.get(key.strftime(key_fmt), 0.0), 2),
        }
        for key in bucket_keys
    ]


def get_recent_invoices(db: Session, limit: int = 6):
    return (
        db.query(Invoice)
        .options(joinedload(Invoice.project).joinedload(Project.customer))
        .order_by(Invoice.created_at.desc())
        .limit(limit)
        .all()
    )


def get_attention_projects(db: Session, limit: int = 8):
    """Two independent reasons a project needs eyes on it:
      1. Not yet delivered, and either Urgent or already past its delivery
         date (the original rule).
      2. Delivered *on credit* (Project.delivered_on_credit) whose invoice
         is still unpaid - this used to disappear from here entirely the
         moment it was delivered (the query required delivered_at IS NULL,
         which a credit delivery obviously fails), even though a delivered-
         but-unpaid order is if anything more worth following up on than
         one still sitting on the shelf. Ordered credit-unpaid-first: once
         the goods are gone there's no more leverage to get paid, so those
         are the most time-sensitive entries here.
    """
    now = datetime.utcnow()
    not_yet_delivered = and_(
        Project.delivered_at.is_(None),
        (Project.priority == "Urgent") | (Project.delivery_date < now),
    )
    credit_unpaid = and_(
        Project.delivered_on_credit.is_(True),
        _latest_invoice_status_subquery() == "pending",
    )
    return (
        db.query(Project)
        .options(joinedload(Project.customer))
        .filter(or_(not_yet_delivered, credit_unpaid))
        .order_by(Project.delivered_on_credit.desc(), Project.delivery_date.asc().nulls_last())
        .limit(limit)
        .all()
    )


def get_recent_deliveries(db: Session, limit: int = 6):
    """Feeds the Dashboard's "Recent Deliveries" panel - the closest thing
    this app has to a delivery notification feed: every project that's
    been marked Delivered, most recent first, each carrying its current
    payment state so a credit delivery reads as "delivered, still unpaid"
    rather than looking indistinguishable from a normal paid-then-
    delivered order."""
    return (
        db.query(Project)
        .options(joinedload(Project.customer))
        .filter(Project.delivered_at.isnot(None))
        .order_by(Project.delivered_at.desc())
        .limit(limit)
        .all()
    )


def get_top_customers(db: Session, limit: int = 5) -> list[dict]:
    rows = (
        db.query(
            Customer.first_name,
            Customer.last_name,
            func.coalesce(func.sum(Invoice.amount), 0.0),
            func.count(Invoice.id),
        )
        .join(Project, Project.customer_id == Customer.id)
        .join(Invoice, Invoice.project_id == Project.id)
        .filter(Invoice.status == "paid")
        .group_by(Customer.id, Customer.first_name, Customer.last_name)
        .order_by(func.sum(Invoice.amount).desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "customer_name": f"{first} {last}",
            "total_spent": round(spent, 2),
            "order_count": count,
        }
        for first, last, spent, count in rows
    ]
