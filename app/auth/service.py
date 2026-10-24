import hmac
from datetime import timedelta
from app.datetime_utils import utcnow
from sqlalchemy.orm import Session
from passlib.hash import bcrypt
from fastapi import HTTPException, status
from app.errors import BadRequest
from app.account_lockout import raise_if_locked, register_failure, register_success
from app.audit import record_audit as record
from app.entities import User
from app.security import create_access_token
from app.email_service import generate_verification_code
from sqlalchemy import select

RESET_CODE_EXPIRY_MINUTES = 15


class AuthService:
    # A bcrypt hash of a value nobody will ever type - verified against on
    # every login for a nonexistent email so this path costs the same ~100ms
    # as a real one. Without it, "no such user" returns instantly while a
    # wrong password takes ~100ms, letting an attacker enumerate valid
    # emails purely by timing the response.
    _DUMMY_HASH = bcrypt.hash("not-a-real-password")

    @staticmethod
    def authenticate_user(db: Session, email: str, password: str):
        user = db.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()

        password_hash = user.hashed_password if user else AuthService._DUMMY_HASH
        password_ok = bcrypt.verify(password, password_hash)

        # A locked account refuses even the right password until the lock
        # expires (see app/account_lockout.py).
        if user:
            raise_if_locked(user)

        if not user or not password_ok:
            if user:
                locked = register_failure(user)
                db.commit()
                if locked:
                    record(db, "system", "auth.lockout", "user", user.id, {"label": user.username})
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        if user.failed_login_count or user.locked_until:
            register_success(user)
            db.commit()
        
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User inactive")
        
        token = create_access_token({"sub": user.username, "role": user.role.value, "tv": user.token_version or 0})
        return token

    # Always returns the same generic outcome regardless of whether the
    # email matches a real account - only sends (and only generates a code)
    # when it does, so a caller can't distinguish "sent" from "no such
    # account" by response content. The controller returns one fixed
    # message either way.
    @staticmethod
    def request_password_reset(db: Session, email: str) -> tuple[str, str] | None:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if not user or not user.is_active:
            return None

        code = generate_verification_code()
        user.reset_code = code
        user.reset_code_expires_at = utcnow() + timedelta(minutes=RESET_CODE_EXPIRY_MINUTES)
        db.commit()

        # (email, code) for the caller to send in the background - sending
        # here would make a real account answer slower than an unknown one.
        return user.email, code

    @staticmethod
    def reset_password(db: Session, email: str, code: str, new_password: str) -> None:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

        valid = (
            user is not None
            and user.reset_code is not None
            and hmac.compare_digest(user.reset_code, code)
            and user.reset_code_expires_at is not None
            and user.reset_code_expires_at >= utcnow()
        )
        if not valid:
            raise BadRequest("Invalid or expired verification code.")

        user.hashed_password = bcrypt.hash(new_password)
        user.revoke_sessions()
        register_success(user)  # a successful reset also clears any lockout
        # Single-use - a code can't be replayed once redeemed, and a fresh
        # forgot-password request overwrites it anyway (see
        # request_password_reset above).
        user.reset_code = None
        user.reset_code_expires_at = None
        db.commit()
