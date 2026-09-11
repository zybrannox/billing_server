from pydantic import BaseModel, EmailStr, Field
from typing import List, Optional
from app.entities import UserRole
from app.projects.model import ProjectRead

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


# The at-a-glance numbers on an employee's profile page - computed once
# server-side (see get_employee_profile) from their assigned/completed
# work, matched by username (Project.assigned_to/*_by are plain strings,
# not a foreign key - there's no other link between a User and their
# projects in this schema).
class EmployeeStats(BaseModel):
    total_assigned: int
    active_assigned: int
    designs_completed: int
    prints_completed: int
    deliveries_completed: int


# Powers GET /users/{id}/profile - identity, every project assigned to
# this employee, and the summary numbers in one call, the same shape as
# CustomerProfile (see app/customers/model.py).
class EmployeeProfile(BaseModel):
    user: UserRead
    stats: EmployeeStats
    projects: List[ProjectRead]