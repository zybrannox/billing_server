from pydantic import BaseModel, EmailStr, Field
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
    # Pydantic v2 does NOT default Optional fields to None on its own - each
    # one needs an explicit `= None`, otherwise it's still required and every
    # partial update would 422 for omitting any field.
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserPasswordUpdate(BaseModel):
    new_password: str = Field(min_length=6)


class UserRead(UserBase):
    id: int

    model_config = {
        "from_attributes": True   # replaces orm_mode=True in Pydantic v2
    }