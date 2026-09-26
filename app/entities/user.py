from typing import Optional
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, Enum, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
import enum
from app.database import Base


class UserRole(enum.Enum):
    ADMIN = "admin"
    USER = "user"
    MODERATOR = "moderator"

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    phone: Mapped[str] = mapped_column(String(15), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255))

    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.USER)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Forgot-password verification code (see app/auth/service.py) - a
    # 6-digit code, not a token, and single-use: cleared the moment it's
    # successfully redeemed or replaced by a fresh forgot-password request.
    reset_code: Mapped[Optional[str]] = mapped_column(String(6), nullable=True)
    reset_code_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        CheckConstraint("phone ~ '^\\+?[0-9]{10,15}$'", name="phone_format_check"),
    )


