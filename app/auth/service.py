from sqlalchemy.orm import Session
from passlib.hash import bcrypt
from fastapi import HTTPException, status
from app.entities import User
from app.security import create_access_token
from sqlalchemy import select


class AuthService:
    @staticmethod
    def authenticate_user(db: Session, email: str, password: str):
        user = db.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()

        if not user or not bcrypt.verify(password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User inactive")
        
        token = create_access_token({"sub": user.username, "role": user.role.value})
        return token
