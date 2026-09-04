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
    top_customers: List[TopCustomer]
