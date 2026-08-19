from fastapi import Depends, Cookie, HTTPException
from jose import jwt, JWTError
from app.config import SECRET_KEY, ALGORITHM

def get_current_user(access_token: str = Cookie(None)):
    if not access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        role = payload.get("role")
        if not username:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"username": username, "role": role}
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Gate for endpoints that expose customer/employee PII - admin role only."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user
