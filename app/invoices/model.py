from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from app.datetime_utils import UTCDateTime, OptionalUTCDateTime

class InvoiceBase(BaseModel):
    project_id: int
    amount: float
    status: str = "pending"
    due_date: OptionalUTCDateTime = None

class InvoiceCreate(InvoiceBase):
    pass

class InvoiceUpdate(BaseModel):
    status: Optional[str] = None
    amount: Optional[float] = None
    due_date: Optional[datetime] = None

class InvoiceRead(InvoiceBase):
    id: int
    invoice_number: str
    created_at: UTCDateTime

    model_config = {"from_attributes": True}


class ProjectSummary(BaseModel):
    id: int
    project_type: str
    description: Optional[str] = None
    start_date: OptionalUTCDateTime = None
    delivery_date: OptionalUTCDateTime = None

    model_config = {"from_attributes": True}


class CustomerSummary(BaseModel):
    first_name: str
    last_name: str
    contact_number: str
    email: str

    model_config = {"from_attributes": True}


class InvoiceDetailRead(InvoiceRead):
    project: Optional[ProjectSummary] = None
    customer: Optional[CustomerSummary] = None


class InvoiceListResponse(BaseModel):
    items: List[InvoiceRead]
    total: int
    page: int
    page_size: int
    total_pages: int
