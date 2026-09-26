from fastapi import APIRouter, Depends, Request, Response, HTTPException
from sqlalchemy.orm import Session

from app.config import IS_PRODUCTION, CLIENT_ACCESS_TOKEN_EXPIRE_MINUTES
from app.database import get_db
from app.auth.dependencies import require_admin
from app.entities import Customer, Company
from app.security import create_client_access_token
from app.rate_limiting import limiter
from .model import (
    ClientLoginRequest,
    ClientMeResponse,
    CreateInviteResponse,
    InviteLookupResponse,
    ActivateAccountRequest,
    ClientForgotPasswordRequest,
    ClientResetPasswordRequest,
)
from .service import ClientAuthService
from .dependencies import get_current_client

router = APIRouter(prefix="/client-auth", tags=["Client Auth"])

COOKIE_KWARGS = dict(
    httponly=True,
    secure=IS_PRODUCTION,
    samesite="none" if IS_PRODUCTION else "lax",
)


def _set_client_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key="client_access_token",
        value=token,
        max_age=CLIENT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        **COOKIE_KWARGS,
    )


@router.post("/login")
@limiter.limit("5/minute")
def login(request: Request, data: ClientLoginRequest, response: Response, db: Session = Depends(get_db)):
    token = ClientAuthService.authenticate_client(db, data.email, data.password)
    _set_client_cookie(response, token)
    return {"message": "Login successful"}


@router.get("/me", response_model=ClientMeResponse)
def read_me(client: dict = Depends(get_current_client), db: Session = Depends(get_db)):
    customer = db.get(Customer, client["customer_id"])
    company = db.get(Company, customer.company_id) if customer.company_id else None
    return ClientMeResponse(
        customer_id=customer.id,
        email=client["email"],
        first_name=customer.first_name,
        last_name=customer.last_name,
        company_id=customer.company_id,
        company_name=company.name if company else None,
    )


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key="client_access_token", **COOKIE_KWARGS)
    return {"message": "Logout successful"}


@router.post("/forgot-password")
@limiter.limit("3/minute")
def forgot_password(request: Request, data: ClientForgotPasswordRequest, db: Session = Depends(get_db)):
    ClientAuthService.request_password_reset(db, data.email)
    return {"message": "If an account exists for that email, a verification code has been sent."}


@router.post("/reset-password")
@limiter.limit("10/minute")
def reset_password(request: Request, data: ClientResetPasswordRequest, db: Session = Depends(get_db)):
    ClientAuthService.reset_password(db, data.email, data.code, data.new_password)
    return {"message": "Password updated successfully."}


# Staff side - granting portal access is staff-invited only, never public
# self-service signup (see app/client_auth service.create_invite).
@router.post("/invite/{customer_id}", response_model=CreateInviteResponse)
def create_invite(
    customer_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    account = ClientAuthService.create_invite(db, customer_id, admin["username"])
    return CreateInviteResponse(
        invite_token=account.invite_token,
        expires_at=account.invite_token_expires_at,
    )


# Public, token-gated - same trust model as GET /public/documents/{token}
# (app/shared_documents): security is the token's own entropy, not a login
# wall, since the whole point is letting someone with no account yet in.
@router.get("/invite/{token}", response_model=InviteLookupResponse)
def lookup_invite(token: str, db: Session = Depends(get_db)):
    result = ClientAuthService.get_invite(db, token)
    if not result:
        return InviteLookupResponse(valid=False)
    customer, company = result
    return InviteLookupResponse(
        valid=True,
        customer_name=f"{customer.first_name} {customer.last_name}",
        company_name=company.name if company else None,
    )


@router.post("/activate")
def activate(payload: ActivateAccountRequest, response: Response, db: Session = Depends(get_db)):
    account = ClientAuthService.activate_account(db, payload.token, payload.email, payload.password)
    # Auto-login on activation, same UX as staff login setting the cookie
    # on success rather than requiring a second round trip.
    token = create_client_access_token({"sub": str(account.id)})
    _set_client_cookie(response, token)
    return {"message": "Account activated"}
