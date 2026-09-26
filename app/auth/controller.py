from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.config import IS_PRODUCTION, ACCESS_TOKEN_EXPIRE_MINUTES
from app.database import get_db
from app.auth.model import LoginRequest, TokenResponse, ForgotPasswordRequest, ResetPasswordRequest
from app.auth.service import AuthService
from app.auth.dependencies import get_current_user
from app.rate_limiting import limiter


router = APIRouter(prefix="/auth", tags=["Auth"])

# By IP, not by the attempted email - rate-limiting per email would let an
# attacker just cycle through target addresses to dodge it, and would also
# let one attacker lock a real user out of their own login attempts.
@router.post("/login")
@limiter.limit("5/minute")
async def login(request: Request, data: LoginRequest, response: Response, db: Session = Depends(get_db)):
    token = AuthService.authenticate_user(db, data.email, data.password)

    # Set HTTP-only cookie.
    # `Secure` cookies are rejected outright by Safari (unlike Chrome, which
    # exempts localhost) when served over plain HTTP, and `SameSite=None`
    # requires `Secure` - so pairing them locally silently drops the cookie
    # and breaks login in Safari. Frontend/backend on localhost are same-site
    # (SameSite only cares about scheme + registrable domain, not port), so
    # `Lax` + non-secure works everywhere in dev; production (real HTTPS,
    # cross-site tunnels) keeps the strict `None` + `Secure` pair.
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=IS_PRODUCTION,
        samesite="none" if IS_PRODUCTION else "lax",
        # Keep the cookie's lifetime in lockstep with the JWT's own expiry -
        # a hardcoded value here previously drifted from
        # ACCESS_TOKEN_EXPIRE_MINUTES, and a too-short cookie logs users out
        # before their (still-valid) token would have expired.
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return {"message": "Login successful"}


@router.get("/me")
async def read_me(current_user: dict = Depends(get_current_user)):
    return current_user


# 3/minute - each successful call sends a real email; without this, the
# endpoint could be used to spam an arbitrary inbox by repeatedly
# "forgetting" their password.
@router.post("/forgot-password")
@limiter.limit("3/minute")
async def forgot_password(request: Request, data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    AuthService.request_password_reset(db, data.email)
    # Same response whether or not the email matched a real account - see
    # AuthService.request_password_reset's own comment.
    return {"message": "If an account exists for that email, a verification code has been sent."}


# 10/minute - the code is 6 digits (1,000,000 possibilities) and expires in
# 15 minutes; capping guesses per IP keeps brute-forcing it impractical
# within that window without needing a per-account lockout.
@router.post("/reset-password")
@limiter.limit("10/minute")
async def reset_password(request: Request, data: ResetPasswordRequest, db: Session = Depends(get_db)):
    AuthService.reset_password(db, data.email, data.code, data.new_password)
    return {"message": "Password updated successfully."}


@router.post("/logout")
async def logout(response: Response):
    # Attributes must mirror set_cookie's (path/domain/samesite/secure) -
    # browsers only clear a cookie when the deletion matches how it was
    # scoped, otherwise the original cookie is left behind untouched and
    # still gets sent on every request as if the user never logged out.
    response.delete_cookie(
        key="access_token",
        httponly=True,
        secure=IS_PRODUCTION,
        samesite="none" if IS_PRODUCTION else "lax",
    )
    return {"message": "Logout successful"}

