from pydantic import BaseModel, Field, field_validator
from typing import List, Literal, Optional
from datetime import datetime
from app.datetime_utils import UTCDateTime, OptionalUTCDateTime

# No payment gateway involved anywhere in this app - these are recorded
# manually by an admin after money changed hands some other way (cash in
# hand, a UPI transfer, etc.), purely for the record.
PaymentMethod = Literal["Cash", "UPI", "Bank Transfer", "Card", "Cheque", "Other"]


class InvoiceItemCreate(BaseModel):
    description: Optional[str] = None
    # Sq-ft billing: width/height must be positive - a zero or negative
    # dimension isn't a real line item. Rate can be 0 (e.g. a comped item)
    # but never negative.
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    rate: float = Field(ge=0)


class InvoiceItemRead(BaseModel):
    id: int
    description: Optional[str] = None
    width: float
    height: float
    sq_ft: float
    rate: float
    total: float
    sort_order: int

    model_config = {"from_attributes": True}


class InvoiceCreate(BaseModel):
    project_id: int
    due_date: OptionalUTCDateTime = None
    # `amount` is deliberately not accepted here - it's derived server-side
    # from `items` (see create_invoice) so a client can never hand the API
    # a total that doesn't match its own line items.
    items: List[InvoiceItemCreate]
    # Flat discount off the items subtotal - see service_create for the
    # "can't exceed the subtotal" check (needs the computed subtotal, so
    # it lives there, not here).
    discount_amount: float = Field(default=0, ge=0)
    # Advance received upfront, entered manually - checked against the
    # post-discount total (what's actually owed), not the raw subtotal -
    # see service_create.
    advance_amount: float = Field(default=0, ge=0)
    payment_method: Optional[PaymentMethod] = None
    payment_reference: Optional[str] = None

    @field_validator("items")
    @classmethod
    def items_must_not_be_empty(cls, v: List[InvoiceItemCreate]) -> List[InvoiceItemCreate]:
        if not v:
            raise ValueError("An invoice needs at least one line item")
        return v


class InvoiceUpdate(BaseModel):
    status: Optional[str] = None
    amount: Optional[float] = None
    due_date: Optional[datetime] = None
    discount_amount: Optional[float] = Field(default=None, ge=0)
    advance_amount: Optional[float] = Field(default=None, ge=0)
    payment_method: Optional[PaymentMethod] = None
    payment_reference: Optional[str] = None


class InvoiceRead(BaseModel):
    id: int
    project_id: int
    subtotal: float
    discount_amount: float
    amount: float
    status: str
    due_date: OptionalUTCDateTime = None
    invoice_number: str
    created_at: UTCDateTime
    advance_amount: float
    payment_method: Optional[str] = None
    payment_reference: Optional[str] = None
    balance_due: float
    # Otherwise the Billing list shows nothing but an auto-numbered
    # INV-2026-XXXXX with no way to tell whose order it is.
    customer_name: Optional[str] = None
    project_type: Optional[str] = None

    model_config = {"from_attributes": True}


class ProjectFileSummary(BaseModel):
    original_name: Optional[str] = None
    # width/height: a physical-size *estimate* in inches, derived client-side
    # from an assumed 96 DPI (see getImageDimensions in the frontend) - not
    # something the file actually declares. Kept for other screens that
    # already display it, but the invoice-creation screen deliberately does
    # NOT use these to auto-fill Width/Height, since a wrong DPI guess would
    # silently feed a wrong size into billing.
    width: Optional[float] = None
    height: Optional[float] = None
    # pixel_width/pixel_height: the file's actual pixel dimensions - a plain
    # fact with no DPI assumption involved. Shown on the invoice-creation
    # screen as a reference so the user can pick an accurate Width/Height
    # themselves instead of trusting an estimate.
    pixel_width: Optional[int] = None
    pixel_height: Optional[int] = None

    model_config = {"from_attributes": True}


class ProjectSummary(BaseModel):
    id: int
    project_type: str
    description: Optional[str] = None
    start_date: OptionalUTCDateTime = None
    delivery_date: OptionalUTCDateTime = None
    # Lets the invoice-creation dialog auto-seed one line item per
    # uploaded design file (see GenerateInvoice.tsx) instead of starting
    # from a single blank row every time.
    files: List[ProjectFileSummary] = []

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
    items: List[InvoiceItemRead] = []


# Returned by GET /invoices/preview/{project_id} - lets the invoice-creation
# screen show "Bill To" / order details before any Invoice row exists yet.
class InvoicePreviewRead(BaseModel):
    project: ProjectSummary
    customer: Optional[CustomerSummary] = None


# Returned by GET /invoices/payment-status/{project_id} - gates the
# "Deliver" action on a project (see Projects.tsx's onMarkDelivered) on
# its most recent invoice actually being paid, not just present.
class ProjectPaymentStatus(BaseModel):
    is_paid: bool
    invoice_number: Optional[str] = None
    invoice_status: Optional[str] = None
    balance_due: Optional[float] = None


class InvoiceListResponse(BaseModel):
    items: List[InvoiceRead]
    total: int
    page: int
    page_size: int
    total_pages: int
