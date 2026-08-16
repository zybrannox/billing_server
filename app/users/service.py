from sqlalchemy.orm import Session
from sqlalchemy import select
from passlib.hash import bcrypt
from app.entities import User, UserRole
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException


class UserService:

    @staticmethod
    def create_user(db: Session, user):

        # check phone exists
        exists = db.execute(
            select(User).where(User.phone == user.phone)
        ).scalar_one_or_none()

        if exists:
            raise HTTPException(status_code=400, detail="Phone already registered")

        # check email exists
        exists = db.execute(
            select(User).where(User.email == user.email)
        ).scalar_one_or_none()

        if exists:
            raise HTTPException(status_code=400, detail="Email already registered")

        hashed_password = bcrypt.hash(user.password)

        new_user = User(
            username=user.username,
            email=user.email,
            phone=user.phone,
            hashed_password=hashed_password,
            role=user.role,
            is_active=user.is_active,
        )

        try:
            db.add(new_user)
            db.commit()
            db.refresh(new_user)

        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=400, detail="Duplicate user data")

        return new_user

    @staticmethod
    def get_all_users(db: Session):
        users = db.execute(select(User)).scalars().all()
        return users
