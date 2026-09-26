from pydantic import BaseModel
from typing import Optional


class PortalProfile(BaseModel):
    customer_id: int
    first_name: str
    last_name: str
    email: Optional[str] = None
    contact_number: str
    company_id: Optional[int] = None
    company_name: Optional[str] = None
