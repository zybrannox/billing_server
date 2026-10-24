"""Session-token behaviour: signing, expiry, tampering, and the staff/client
boundary. These pin the guarantees the auth layer relies on, independent of
which JWT library implements them."""
from datetime import timedelta
from app.datetime_utils import utcnow

import jwt
import pytest
from fastapi import HTTPException
from passlib.hash import bcrypt

from app.auth.dependencies import get_current_user
from app.client_auth.dependencies import get_current_client
from app.config import ALGORITHM, CLIENT_SECRET_KEY, SECRET_KEY
from app.entities import User, UserRole
from app.security import create_access_token, create_client_access_token


@pytest.fixture
def staff(db):
    user = User(
        username="alan",
        email="alan@example.com",
        phone="9876543210",
        hashed_password=bcrypt.hash("a long enough password"),
        role=UserRole.USER,
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


def test_staff_token_round_trips(db, staff):
    token = create_access_token({"sub": "alan"})
    assert get_current_user(access_token=token, db=db) == {"username": "alan", "role": "user"}


def test_staff_and_client_tokens_are_mutually_undecodable():
    staff_token = create_access_token({"sub": "1"})
    client_token = create_client_access_token({"sub": "1"})
    with pytest.raises(jwt.PyJWTError):
        jwt.decode(staff_token, CLIENT_SECRET_KEY, algorithms=[ALGORITHM])
    with pytest.raises(jwt.PyJWTError):
        jwt.decode(client_token, SECRET_KEY, algorithms=[ALGORITHM])


def test_a_staff_token_is_refused_by_the_client_dependency(db):
    with pytest.raises(HTTPException) as err:
        get_current_client(client_access_token=create_access_token({"sub": "1"}), db=db)
    assert err.value.status_code == 401


def test_expired_token_is_refused(db, staff):
    expired = jwt.encode({"sub": "alan", "exp": utcnow() - timedelta(minutes=1)}, SECRET_KEY, algorithm=ALGORITHM)
    with pytest.raises(HTTPException) as err:
        get_current_user(access_token=expired, db=db)
    assert err.value.status_code == 401


def test_tampered_token_is_refused(db, staff):
    token = create_access_token({"sub": "alan"})
    header, payload, signature = token.split(".")
    forged = ".".join([header, payload, signature[:-4] + ("AAAA" if not signature.endswith("AAAA") else "BBBB")])
    with pytest.raises(HTTPException):
        get_current_user(access_token=forged, db=db)


def test_unsigned_alg_none_token_is_refused(db, staff):
    unsigned = jwt.encode({"sub": "alan"}, key=None, algorithm="none")
    with pytest.raises(HTTPException):
        get_current_user(access_token=unsigned, db=db)


def test_token_signed_with_the_wrong_key_is_refused(db, staff):
    forged = jwt.encode({"sub": "alan", "exp": utcnow() + timedelta(hours=1)}, "x" * 48, algorithm=ALGORITHM)
    with pytest.raises(HTTPException):
        get_current_user(access_token=forged, db=db)


def test_valid_token_for_a_deactivated_user_is_refused(db, staff):
    token = create_access_token({"sub": "alan"})
    staff.is_active = False
    db.commit()
    with pytest.raises(HTTPException) as err:
        get_current_user(access_token=token, db=db)
    assert err.value.status_code == 401


def test_missing_cookie_is_refused(db):
    with pytest.raises(HTTPException) as err:
        get_current_user(access_token=None, db=db)
    assert err.value.status_code == 401
