"""A customer typed straight into a form: Add Project, Create Invoice, Create Quotation."""
import re

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.entities.customer import Customer
from app.errors import BadRequest


class NewCustomer(BaseModel):
    name: str = Field(max_length=100)
    contact_number: str

    @field_validator("name")
    @classmethod
    def name_is_tidy(cls, value: str) -> str:
        name = " ".join(value.split())
        if not name:
            raise ValueError("Enter the customer's name")
        return name

    # Same rule as the customers table's own check, after dropping what people
    # naturally type between the digits.
    @field_validator("contact_number")
    @classmethod
    def phone_is_valid(cls, value: str) -> str:
        phone = re.sub(r"[\s()-]", "", value)
        if not re.fullmatch(r"\+?[0-9]{10,15}", phone) or len(phone) > 15:
            raise ValueError("Enter a valid phone number")
        return phone


def customer_from_form(db: Session, new_customer: NewCustomer) -> Customer:
    """The customer just typed in, reusing them when the same name and number are
    already saved. A shared number alone isn't enough: several real customers
    have one. Only flushed, so it commits or fails together with what it's for."""
    same_number = db.query(Customer).filter(
        Customer.contact_number == new_customer.contact_number,
        Customer.is_placeholder.is_(False),
    )
    for customer in same_number:
        if " ".join(f"{customer.first_name} {customer.last_name}".split()).casefold() == new_customer.name.casefold():
            return customer

    first_name, _, last_name = new_customer.name.partition(" ")
    customer = Customer(first_name=first_name, last_name=last_name, contact_number=new_customer.contact_number)
    db.add(customer)
    db.flush()
    return customer


def refuse_placeholder(customer: Customer | None) -> None:
    """Older work keeps the catch-all customer, but new work can't use it."""
    if customer and customer.is_placeholder:
        raise BadRequest("Pick a real customer, or enter their name and phone number.")
