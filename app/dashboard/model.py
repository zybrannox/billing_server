from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from app.datetime_utils import OptionalUTCDateTime, UTCDateTime


class DashboardStats(BaseModel):
    total_customers: int
    total_projects: int
    active_projects: int  # print_status != "Completed"
    completed_projects: int  # print_status == "Completed"
    delivered_projects: int  # delivered_at is not null
    total_revenue: float  # sum(amount) of paid invoices, all-time
    revenue_this_month: float  # sum(amount) of paid invoices, current month
    outstanding_balance: float  # sum(balance_due) of pending invoices
    pending_invoices: int
    overdue_invoices: int  # pending and past due_date


class StatusCount(BaseModel):
    label: str
    count: int


class RevenuePoint(BaseModel):
    period: str  # "Mar 2026"
    revenue: float


class RecentInvoice(BaseModel):
    id: int
    invoice_number: str
    customer_name: Optional[str] = None
    project_type: Optional[str] = None
    amount: float
    status: str
    created_at: UTCDateTime

    model_config = {"from_attributes": True}


class AttentionProject(BaseModel):
    id: int
    project_type: str
    customer_name: Optional[str] = None
    priority: str
    print_status: str
    delivery_date: OptionalUTCDateTime = None
    is_overdue: bool
    # True when this row is here because it was delivered on credit and
    # is still unpaid (see get_attention_projects) - distinct from
    # is_overdue, since a delivered project's delivery_date is no longer
    # the relevant deadline; what matters now is collecting payment.
    is_credit_unpaid: bool = False

    model_config = {"from_attributes": True}


class RecentDelivery(BaseModel):
    id: int
    project_type: str
    customer_name: Optional[str] = None
    delivered_at: UTCDateTime
    delivered_by: Optional[str] = None
    delivered_on_credit: bool
    # The project's current invoice status ("paid"/"pending"/"cancelled"),
    # or null if it somehow has no invoice at all. Lets the panel show a
    # credit delivery as "still unpaid" right up until it's actually
    # settled, rather than looking identical to a normal delivery.
    payment_status: Optional[str] = None

    model_config = {"from_attributes": True}


class TopCustomer(BaseModel):
    customer_name: str
    total_spent: float
    order_count: int


class DashboardSummary(BaseModel):
    stats: DashboardStats
    project_status_breakdown: List[StatusCount]
    priority_breakdown: List[StatusCount]
    revenue_trend: List[RevenuePoint]
    recent_invoices: List[RecentInvoice]
    attention_projects: List[AttentionProject]
    recent_deliveries: List[RecentDelivery]
    top_customers: List[TopCustomer]
