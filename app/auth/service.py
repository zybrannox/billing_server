from sqlalchemy.orm import Session
from passlib.hash import bcrypt
from fastapi import HTTPException, status
from app.entities import User
from app.security import create_access_token
from sqlalchemy import select


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
