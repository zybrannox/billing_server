from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from app.config import IS_PRODUCTION
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
        max_age=3600        # 1 hour
    )
    return {"message": "Login successful"}


@router.get("/me")
async def read_me(current_user: dict = Depends(get_current_user)):
    return current_user

