from typing import Optional
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, Enum, CheckConstraint, Integer
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

    # Server-side session revocation: tokens carry this number ("tv") and stop
    # working the moment it changes (password change/reset, "sign out
    # everywhere"). Bumped via the entity's revoke_sessions().
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # Per-account brute-force lockout (see app/account_lockout.py): the
    # per-IP rate limit alone doesn't stop a slow attack spread over many IPs.
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    def revoke_sessions(self) -> None:
        self.token_version = (self.token_version or 0) + 1

    __table_args__ = (
        CheckConstraint("phone ~ '^\\+?[0-9]{10,15}$'", name="phone_format_check"),
    )


