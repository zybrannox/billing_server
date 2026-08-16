from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class InvoiceBase(BaseModel):
    project_id: int
    invoice_number: str
    amount: float
    status: str = "pending"
    due_date: Optional[datetime] = None

class InvoiceCreate(InvoiceBase):
    pass

class InvoiceUpdate(BaseModel):
    status: Optional[str] = None
    amount: Optional[float] = None
    due_date: Optional[datetime] = None

class InvoiceRead(InvoiceBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True
