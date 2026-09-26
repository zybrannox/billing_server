from pydantic import BaseModel
from typing import List, Optional
from app.datetime_utils import UTCDateTime
from app.customers.model import CustomerRead


class CompanyBase(BaseModel):
    name: str
    billing_email: Optional[str] = None
    phone: Optional[str] = None
    billing_address: Optional[str] = None
    payment_terms_days: int = 0
    credit_limit: Optional[float] = None
    notes: Optional[str] = None


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    billing_email: Optional[str] = None
    phone: Optional[str] = None
    billing_address: Optional[str] = None
    payment_terms_days: Optional[int] = None
    credit_limit: Optional[float] = None
    notes: Optional[str] = None


class CompanyRead(CompanyBase):
    id: int
    created_at: UTCDateTime

    model_config = {"from_attributes": True}


class CompanyListResponse(BaseModel):
    items: List[CompanyRead]
    total: int
    page: int
    page_size: int
    total_pages: int


# Mirrors CustomerStats, aggregated across every contact (Customer row
# with this company_id) instead of one customer's own history - see
# CompanyService.get_company_profile.
class CompanyStats(BaseModel):
    total_contacts: int
    total_orders: int
    active_orders: int
    total_spent: float
    outstanding_balance: float
    total_invoices: int
    pending_invoices: int


# Powers GET /companies/{id}/profile. Deliberately no embedded invoices
# list (unlike CustomerProfile) - a company's invoice volume aggregated
# across every contact can outgrow a capped in-memory list in a way one
# customer's own history won't, so the profile page's Billing tab fetches
# its own paginated GET /invoices/?company_id=X instead (see
# app/invoices/repository.py's get_all_invoices).
class CompanyProfile(BaseModel):
    company: CompanyRead
    stats: CompanyStats
    contacts: List[CustomerRead]
