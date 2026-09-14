from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Literal, Optional
from datetime import datetime
from app.datetime_utils import UTCDateTime, OptionalUTCDateTime

# No payment gateway involved anywhere in this app - these are recorded
# manually by an admin after money changed hands some other way (cash in
# hand, a UPI transfer, etc.), purely for the record.
PaymentMethod = Literal["Cash", "UPI", "Bank Transfer", "Card", "Cheque", "Other"]

# Not every job is naturally measured in feet - a name board is more
# usefully entered as "18in x 6in" than "1.5ft x 0.5ft". The rate stays
# per-square-foot regardless (see calculations.compute_line, which
# converts sq inches -> sq ft at 144 sq in/sq ft when unit="in"); this
# only changes what unit width/height were actually typed in.
MeasurementUnit = Literal["ft", "in"]


class InvoiceItemCreate(BaseModel):
    description: Optional[str] = None
    # Sq-ft billing: width/height must be positive - a zero or negative
    # dimension isn't a real line item. Rate can be 0 (e.g. a comped item)
    # but never negative.
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    unit: MeasurementUnit = "ft"
    rate: float = Field(ge=0)
    # How many identical pieces this one line bills for (e.g. 10 identical
    # name boards at the same size/rate) - `total` is width x height x
    # rate x pieces (see calculations.compute_line), so this is a real
    # multiplier on the bill, not just a display note.
    pieces: int = Field(default=1, ge=1)
    # True when the client typed a Total directly and back-derived this
    # rate from it (rate = total ÷ area) rather than the rate being what
    # was actually entered - see InvoiceItem.is_manual_total. `rate` is
    # still required and still drives the stored total either way; this
    # only controls whether the invoice view shows it.
    is_manual_total: bool = False


class InvoiceItemRead(BaseModel):
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


# Lets an invoice be raised for a job that has no project record yet - the
# admin topbar's "Create Invoice" shortcut (see GenerateInvoice.tsx) is a
# single-page, single-submit screen like a Zoho Books invoice: just who
# it's billed to, what it's for, and the line items - not a work-tracking
# form. The Project and Invoice are still created together in one
# transaction (see repository.create_invoice), but neither the
# project-management fields a real tracked job would have (assignee,
# priority, client status, start/delivery dates) nor a free-text
# description are asked for here - a real invoice doesn't carry a job
# description, just what's billed on it (the line items already say what
# each item is). Assignee/priority/etc. get fixed defaults server-side
# (see create_invoice), since this project exists purely to hang the
# invoice off of, not to be scheduled or assigned like ordinary work
# coming through Projects.
class InvoiceNewProject(BaseModel):
    project_type: str
    customer_id: int


class InvoiceCreate(BaseModel):
    # Exactly one of these must be set (see exactly_one_project_source) -
    # project_id for invoicing a job already tracked as a Project,
    # new_project to raise the invoice and create that Project together.
    project_id: Optional[int] = None
    new_project: Optional[InvoiceNewProject] = None
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

    @model_validator(mode="after")
    def exactly_one_project_source(self):
        if bool(self.project_id) == bool(self.new_project):
            raise ValueError(
                "Provide either project_id (an existing project) or new_project (to create one), not both or neither"
            )
        return self


class InvoiceUpdate(BaseModel):
    status: Optional[str] = None
    amount: Optional[float] = None
    due_date: Optional[datetime] = None
    discount_amount: Optional[float] = Field(default=None, ge=0)
    advance_amount: Optional[float] = Field(default=None, ge=0)
    payment_method: Optional[PaymentMethod] = None
    payment_reference: Optional[str] = None
    # Set by service_update/service_mark_paid when a status change lands on
    # "paid" (see app/invoices/service.py) - not meant to be set directly
    # by a caller, same as `amount` above.
    paid_at: Optional[datetime] = None


# Body for PATCH /invoices/{id}/mark-paid - deliberately just these two
# fields, not the full InvoiceUpdate. That endpoint is open to any
# authenticated user (see controller.py); this narrow shape is what keeps
# it from also becoming a route to the discount/amount edits that stay
# admin-only via the generic PATCH /invoices/{id}.
class MarkInvoicePaidRequest(BaseModel):
    payment_method: PaymentMethod
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
    # A customer's invoices often share the same project_type - this is
    # what actually distinguishes one job from another at a glance (see
    # entities/invoice.py's project_description property).
    project_description: Optional[str] = None

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
    # Optional to match customers.email actually being nullable in the DB
    # (see the make_customer_email_optional migration) - a required `str`
    # here crashed this response with a 500 (ResponseValidationError) for
    # any customer that had no email on file.
    email: Optional[str] = None

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
