from fastapi import Depends, Cookie, HTTPException
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.config import CLIENT_SECRET_KEY, ALGORITHM
from app.database import get_db
from app.entities import ClientAccount, Customer


def get_current_client(client_access_token: str = Cookie(None), db: Session = Depends(get_db)) -> dict:
    """Client-portal equivalent of app/auth/dependencies.py's
    get_current_user - decoded with CLIENT_SECRET_KEY only, so a staff
    token (signed with the unrelated SECRET_KEY) can never pass here, and
    vice versa. No require_client on top of this - clients have no role
    split the way staff does."""
    if not client_access_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(client_access_token, CLIENT_SECRET_KEY, algorithms=[ALGORITHM])
        account_id = payload.get("sub")
        if not account_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    account = db.get(ClientAccount, int(account_id))
    if not account or not account.is_active or account.activated_at is None:
        raise HTTPException(status_code=401, detail="Account no longer exists or is inactive")

    customer = db.get(Customer, account.customer_id)
    if not customer:
        raise HTTPException(status_code=401, detail="Linked customer no longer exists")

    return {
        "client_account_id": account.id,
        "customer_id": customer.id,
        "email": account.email,
        "company_id": customer.company_id,
    }
