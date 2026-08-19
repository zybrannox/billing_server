from fastapi import Depends, Cookie, HTTPException
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.config import SECRET_KEY, ALGORITHM
from app.database import get_db
from app.entities import User

def get_current_user(access_token: str = Cookie(None), db: Session = Depends(get_db)):
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
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

    return {"username": user.username, "role": user.role.value}


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Gate for endpoints that expose customer/employee PII - admin role only."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
