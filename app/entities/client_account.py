from typing import Optional
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class ClientAccount(Base):
    """Portal login for a client (an individual Customer, or a B2B Company
    contact - see entities/customer.py, a "contact" is just a Customer row
    with company_id set). Deliberately its own table and its own JWT secret
    (see app/security.py's create_client_access_token / CLIENT_SECRET_KEY in
    app/config.py) rather than a new value on UserRole - staff and clients
    must never be mutually valid principals, see app/client_auth.

    No relationship() - customer_id is a plain FK, joined explicitly in
    app/client_auth/service.py, matching Customer/Company's own style.
    """

    __tablename__ = "client_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    # The portal login identity - deliberately separate from Customer.email
    # (business contact info, optional, editable by staff) and null until
    # the client actually activates their invite.
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # Staff kill-switch, independent of activation state - deactivating a
    # client shouldn't require deleting their account/history.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    invite_token: Mapped[Optional[str]] = mapped_column(String(64), unique=True, index=True, nullable=True)
    invite_token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    invited_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    invited_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Forgot-password verification code (see app/client_auth/service.py) -
    # separate from invite_token above: invite_token is for first-time
    # account setup (no password exists yet), this is for an already-
    # activated client who forgot their password.
    reset_code: Mapped[Optional[str]] = mapped_column(String(6), nullable=True)
    reset_code_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
