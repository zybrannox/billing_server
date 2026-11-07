from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.datetime_utils import OptionalUTCDateTime, UTCDateTime
from app.invoices.model import PaymentMethod
from app.response_model import ResponseModel


class Allocation(BaseModel):
    """How much of a payment goes to one invoice."""

    invoice_id: int
    amount: float = Field(gt=0)


def _distinct(allocations: List[Allocation]) -> List[Allocation]:
    ids = [a.invoice_id for a in allocations]
    if len(ids) != len(set(ids)):
        raise ValueError("Each invoice can appear only once")
    return allocations


class CustomerPaymentCreate(BaseModel):
    amount: float = Field(gt=0, le=100_000_000)
    payment_method: PaymentMethod
    payment_reference: Optional[str] = Field(default=None, max_length=100)
    note: Optional[str] = Field(default=None, max_length=500)
    # When the customer paid. Defaults to now; can be earlier, never later.
    received_at: Optional[datetime] = None
    # Whatever isn't allocated stays with the customer as credit.
    allocations: List[Allocation] = []

    @field_validator("allocations")
    @classmethod
    def each_invoice_once(cls, v: List[Allocation]) -> List[Allocation]:
        return _distinct(v)


class ApplyCredit(BaseModel):
    allocations: List[Allocation] = Field(min_length=1)

    @field_validator("allocations")
    @classmethod
    def each_invoice_once(cls, v: List[Allocation]) -> List[Allocation]:
        return _distinct(v)


class OpenInvoice(ResponseModel):
    """An unpaid invoice a payment can go to, oldest first."""

    id: int
    invoice_number: Optional[str]
    created_at: UTCDateTime
    due_date: OptionalUTCDateTime
    job: Optional[str]
    amount: float
    balance_due: float


class AppliedTo(ResponseModel):
    invoice_id: int
    invoice_number: Optional[str]
    amount: float


class CustomerPaymentRead(ResponseModel):
    id: int
    customer_id: int
    amount: float
    payment_method: str
    payment_reference: Optional[str]
    note: Optional[str]
    received_at: UTCDateTime
    recorded_by: Optional[str]
    created_at: UTCDateTime
    # Net per invoice (a reversed share nets to nothing and is left out).
    applied_to: List[AppliedTo]
    unused: float


class CustomerPaymentList(ResponseModel):
    items: List[CustomerPaymentRead]
    # Everything this customer has paid that isn't on an invoice yet.
    credit: float
