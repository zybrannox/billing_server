from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from app.config import IS_PRODUCTION, ACCESS_TOKEN_EXPIRE_MINUTES
from app.database import get_db
from app.auth.model import LoginRequest, TokenResponse
from app.auth.service import AuthService
from app.auth.dependencies import get_current_user


router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/login")
async def login(data: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
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

