from pydantic import BaseModel, Field, field_validator
from typing import List, Literal, Optional
from app.datetime_utils import UTCDateTime, OptionalUTCDateTime
from app.projects.model import Priority
from app.invoices.model import MeasurementUnit


class QuotationItemCreate(BaseModel):
    description: Optional[str] = None
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    unit: MeasurementUnit = "ft"
    rate: float = Field(ge=0)
    # See app/invoices/model.py's InvoiceItemCreate.pieces - identical
    # meaning, carried straight over on conversion to an invoice.
    pieces: int = Field(default=1, ge=1)
    is_manual_total: bool = False


class QuotationItemRead(BaseModel):
    id: int
    description: Optional[str] = None
    width: float
    height: float
    unit: MeasurementUnit
    sq_ft: float
    rate: float
    pieces: int
    total: float
    is_manual_total: bool
    sort_order: int

    model_config = {"from_attributes": True}


class QuotationCreate(BaseModel):
    customer_id: int
    project_type: str
    valid_until: OptionalUTCDateTime = None
    items: List[QuotationItemCreate]
    discount_amount: float = Field(default=0, ge=0)

    @field_validator("items")
    @classmethod
    def items_must_not_be_empty(cls, v: List[QuotationItemCreate]) -> List[QuotationItemCreate]:
        if not v:
            raise ValueError("A quotation needs at least one line item")
        return v


# Body for PATCH /quotations/{id}/status - deliberately narrow (just the
# customer's decision), not a generic update - a quotation's own numbers are
# fixed once raised, same reasoning as invoices never letting amount/items
# be edited in place after creation.
class QuotationStatusUpdate(BaseModel):
    status: Literal["accepted", "rejected"]


# Body for POST /quotations/{id}/convert - the project-level details a
# quotation never asked for while it was just an estimate (who does the
# work, when) so they're only collected once the customer has actually
# said yes. Everything else (customer, job type, line items, discount)
# already lives on the quotation and carries straight over.
class QuotationConvertRequest(BaseModel):
    assigned_to: str
    priority: Priority
    client_status: str
    start_date: UTCDateTime
    delivery_date: UTCDateTime


class CustomerSummary(BaseModel):
    first_name: str
    last_name: str
    contact_number: str
    email: Optional[str] = None

    model_config = {"from_attributes": True}


class QuotationRead(BaseModel):
    id: int
    quotation_number: str
    customer_id: int
    project_type: str
    subtotal: float
    discount_amount: float
    amount: float
    status: str
    valid_until: OptionalUTCDateTime = None
    created_at: UTCDateTime
    converted_project_id: Optional[int] = None
    converted_invoice_id: Optional[int] = None
    customer_name: Optional[str] = None

    model_config = {"from_attributes": True}


class QuotationDetailRead(QuotationRead):
    customer: Optional[CustomerSummary] = None
    items: List[QuotationItemRead] = []


class QuotationListResponse(BaseModel):
    items: List[QuotationRead]
    total: int
    page: int
    page_size: int
    total_pages: int
