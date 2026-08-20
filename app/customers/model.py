from pydantic import BaseModel, EmailStr
from typing import List, Optional


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

    model_config = {
        "from_attributes": True
    }


class CustomerListResponse(BaseModel):
    items: List[CustomerRead]
    total: int
    page: int
    page_size: int
    total_pages: int
