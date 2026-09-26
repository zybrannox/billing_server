from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from app.datetime_utils import UTCDateTime


class ClientLoginRequest(BaseModel):
    email: EmailStr
    password: str


class ClientMeResponse(BaseModel):
    customer_id: int
    email: Optional[str] = None
    first_name: str
    last_name: str
    company_id: Optional[int] = None
    company_name: Optional[str] = None


# Deliberately doesn't build the full activation URL server-side - no
# FRONTEND_URL env var exists anywhere in this codebase (every cross-page
# link is built client-side from window.location.origin), so the frontend
# builds `${origin}/portal/activate?token=...` itself, same convention.
class CreateInviteResponse(BaseModel):
    invite_token: str
    expires_at: UTCDateTime


class InviteLookupResponse(BaseModel):
    valid: bool
    customer_name: Optional[str] = None
    company_name: Optional[str] = None


class ActivateAccountRequest(BaseModel):
    token: str
    email: EmailStr
    password: str


class ClientForgotPasswordRequest(BaseModel):
    email: EmailStr


class ClientResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)
    new_password: str = Field(min_length=6)
