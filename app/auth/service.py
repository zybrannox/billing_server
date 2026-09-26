from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from passlib.hash import bcrypt
from fastapi import HTTPException, status
from app.entities import User
from app.security import create_access_token
from app.email_service import generate_verification_code, send_password_reset_code
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

        if not user or not password_ok:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User inactive")
        
        token = create_access_token({"sub": user.username, "role": user.role.value})
        return token

    # Always returns the same generic outcome regardless of whether the
    # email matches a real account - only sends (and only generates a code)
    # when it does, so a caller can't distinguish "sent" from "no such
    # account" by response content. The controller returns one fixed
    # message either way.
    @staticmethod
    def request_password_reset(db: Session, email: str) -> None:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if not user or not user.is_active:
            return

        code = generate_verification_code()
        user.reset_code = code
        user.reset_code_expires_at = datetime.utcnow() + timedelta(minutes=RESET_CODE_EXPIRY_MINUTES)
        db.commit()

        send_password_reset_code(user.email, code)

    @staticmethod
    def reset_password(db: Session, email: str, code: str, new_password: str) -> None:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

        valid = (
            user is not None
            and user.reset_code is not None
            and user.reset_code == code
            and user.reset_code_expires_at is not None
            and user.reset_code_expires_at >= datetime.utcnow()
        )
        if not valid:
            raise HTTPException(status_code=400, detail="Invalid or expired verification code.")

        user.hashed_password = bcrypt.hash(new_password)
        # Single-use - a code can't be replayed once redeemed, and a fresh
        # forgot-password request overwrites it anyway (see
        # request_password_reset above).
        user.reset_code = None
        user.reset_code_expires_at = None
        db.commit()
