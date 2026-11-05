from fastapi import Depends, Cookie, HTTPException
import jwt  # PyJWT
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.config import SECRET_KEY, ALGORITHM
from app.database import get_db
from app.entities import User, UserRole

def _permissions_of(user: User) -> list[str]:
    # Local import: permissions.py builds on this module's get_current_user.
    from .permissions import ALL_PERMISSIONS

    if user.role == UserRole.ADMIN:
        return list(ALL_PERMISSIONS)
    return [p for p in ALL_PERMISSIONS if p in (user.permissions or [])]


def get_current_user(access_token: str = Cookie(None), db: Session = Depends(get_db)):
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    # The JWT's claims are only a snapshot from login time - without this,
    # a deleted or deactivated user's already-issued token (up to
    # ACCESS_TOKEN_EXPIRE_MINUTES old) keeps working until it naturally
    # expires, since nothing else re-checks the database on each request.
    user = db.execute(
        select(User).where(User.username == username)
    ).scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User no longer exists or is inactive")
    # A username can be edited and later reused by someone else, so the name
    # alone doesn't prove this is the same person - without this, a session
    # still open under the old name would silently become the new owner's
    # account. Tokens issued before this claim existed simply don't have it.
    if payload.get("uid", user.id) != user.id:
        raise HTTPException(status_code=401, detail="Session has been signed out")
    # Revoked (password changed/reset, "sign out everywhere"). Tokens issued
    # before this claim existed count as version 0.
    if payload.get("tv", 0) != (user.token_version or 0):
        raise HTTPException(status_code=401, detail="Session has been signed out")

    # Who the activity log credits for what this request changes (app/audit/tracker.py).
    db.info["actor"] = user.username
    return {"username": user.username, "role": user.role.value, "permissions": _permissions_of(user)}


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Gate for endpoints that expose customer/employee PII - admin role only."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
