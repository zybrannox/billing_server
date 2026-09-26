from datetime import datetime, timedelta
from jose import jwt
from app.config import (
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    CLIENT_SECRET_KEY,
    CLIENT_ACCESS_TOKEN_EXPIRE_MINUTES,
)

def create_access_token(data: dict):
    """
    Create a JWT token with expiration.
    data: dict containing user info, e.g., {"sub": email, "role": role}
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return token


def create_client_access_token(data: dict):
    """Sibling to create_access_token, signed with CLIENT_SECRET_KEY - see
    app/client_auth. Keeps staff and client tokens mutually undecodable
    regardless of what claims either side happens to carry."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=CLIENT_ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    token = jwt.encode(to_encode, CLIENT_SECRET_KEY, algorithm=ALGORITHM)
    return token
