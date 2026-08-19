from sqlalchemy import String, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    contact_number: Mapped[str] = mapped_column(String(15))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)

    __table_args__ = (
        CheckConstraint("contact_number ~ '^\\+?[0-9]{10,15}$'", name="customer_phone_format_check"),
    )
