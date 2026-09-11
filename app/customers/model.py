from pydantic import BaseModel, EmailStr
from typing import List, Literal, Optional
from app.projects.model import ProjectRead
from app.invoices.model import InvoiceRead


class CustomerBase(BaseModel):
    first_name: str
    last_name: str
    contact_number: str
    email: Optional[EmailStr] = None


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    contact_number: Optional[str] = None
    email: Optional[EmailStr] = None


class CustomerRead(CustomerBase):
    id: int
    # Attached only by the list endpoint (see CustomerService.get_all_
    # customers) - a plain single-customer fetch (e.g. the customer-profile
    # page, which computes its own richer stats separately) leaves these
    # None rather than paying for the extra query.
    payment_status: Optional[Literal["paid", "pending", "no_invoices"]] = None
    outstanding_balance: Optional[float] = None

    model_config = {
        "from_attributes": True
    }


class CustomerListResponse(BaseModel):
    items: List[CustomerRead]
    total: int
    page: int
    page_size: int
    total_pages: int


# The at-a-glance numbers on a customer's profile page - computed once
# server-side (see get_customer_profile) rather than making the frontend
# re-derive them from the full orders/invoices lists on every render.
class CustomerStats(BaseModel):
    total_orders: int
    active_orders: int
    # Money actually collected (sum of paid invoices), distinct from
    # outstanding_balance below (money still owed on unpaid ones) - the
    # two intentionally don't add up to "everything ever invoiced" since
    # a cancelled invoice counts toward neither.
    total_spent: float
    outstanding_balance: float
    pending_invoices: int


# Powers GET /customers/{id}/profile - one call for the whole profile page
# (identity, every order, every invoice, and the summary numbers) instead
# of the frontend firing three separate requests and assembling them itself.
class CustomerProfile(BaseModel):
    customer: CustomerRead
    stats: CustomerStats
    projects: List[ProjectRead]
    invoices: List[InvoiceRead]
