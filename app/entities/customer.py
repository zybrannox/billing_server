from typing import Optional

from sqlalchemy import Boolean, String, CheckConstraint, ForeignKey, false
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    contact_number: Mapped[str] = mapped_column(String(15))
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True, nullable=True)
    # A "contact" isn't its own entity - it's just a Customer row that
    # optionally belongs to a B2B Company (see entities/company.py),
    # sharing that company's billing terms instead of being invoiced on
    # its own. ON DELETE SET NULL: deleting a company detaches its
    # contacts rather than failing or cascading into deleting customers
    # who still have their own project/invoice history.
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # A catch-all for jobs with no real customer. Older projects keep pointing at
    # it, but it's no longer offered for new ones.
    is_placeholder: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    __table_args__ = (
        CheckConstraint("contact_number ~ '^\\+?[0-9]{10,15}$'", name="customer_phone_format_check"),
    )
