from pydantic import BaseModel, EmailStr
from typing import Optional
from app.entities import UserRole

class UserBase(BaseModel):
    username: str
    email: EmailStr
    phone: str
    role: Optional[UserRole] = UserRole.USER
    is_active: Optional[bool] = True


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    username: Optional[str]
    phone: Optional[str]
    role: Optional[UserRole]
    is_active: Optional[bool]


class UserRead(UserBase):
    id: int

    model_config = {
        "from_attributes": True   # replaces orm_mode=True in Pydantic v2
    }