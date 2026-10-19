from sqlalchemy.orm import Session

from app.entities.company import Company
from app.entities.customer import Customer


def customer_bill_to(db: Session, customer: Customer | None) -> dict | None:
    """The customer as a printed document's "Billed To" block needs it: the
    contact's own details plus, for a B2B contact, the company's name and
    billing address (Customer has no address of its own). Returned as a
    plain dict so it validates into CustomerSummary like the ORM object
    did."""
    if customer is None:
        return None
    company = db.get(Company, customer.company_id) if customer.company_id else None
    return {
        "first_name": customer.first_name,
        "last_name": customer.last_name,
        "contact_number": customer.contact_number,
        "email": customer.email,
        "company_name": company.name if company else None,
        "company_address": company.billing_address if company else None,
    }
