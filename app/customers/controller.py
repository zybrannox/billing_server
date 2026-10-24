from app.pagination import page_count
from typing import Literal

from fastapi import APIRouter, Depends, Query
from app.errors import NotFound
from sqlalchemy.orm import Session

from app.database import get_db
from app.audit import record_audit, label_of
from app.entities import Customer
from app.auth.dependencies import require_admin, get_current_user
from app.customers.model import CustomerCreate, CustomerUpdate, CustomerRead, CustomerListResponse, CustomerProfile
from app.customers.service import CustomerService

router = APIRouter(prefix="/customers", tags=["Customers"])


@router.post("/", response_model=CustomerRead)
def create_customer(
    customer: CustomerCreate,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    return CustomerService.create_customer(db, customer)


@router.get("/", response_model=CustomerListResponse)
def get_customers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    sort: Literal["name", "most_used"] = Query("name"),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    items, total = CustomerService.get_all_customers(
        db, page=page, page_size=page_size, search=search, sort=sort
    )
    total_pages = page_count(total, page_size)
    return CustomerListResponse(
        items=items, total=total, page=page, page_size=page_size, total_pages=total_pages
    )


@router.get("/{customer_id}", response_model=CustomerRead)
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    customer = CustomerService.get_customer_by_id(db, customer_id)

    if not customer:
        raise NotFound("Customer")

    return customer


# Powers the admin Customer Profile page (clicking a customer in the
# Customers table) - identity, every order, every invoice, and the summary
# numbers in one call. Admin-only like the Billing page this replaces, since
# it surfaces the same financial detail (amounts, balances, invoice status).
@router.get("/{customer_id}/profile", response_model=CustomerProfile)
def get_customer_profile(
    customer_id: int,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    profile = CustomerService.get_customer_profile(db, customer_id)

    if not profile:
        raise NotFound("Customer")

    return profile


@router.put("/{customer_id}", response_model=CustomerRead)
def update_customer(
    customer_id: int,
    update: CustomerUpdate,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    updated = CustomerService.update_customer(db, customer_id, update)

    if not updated:
        raise NotFound("Customer")

    return updated


@router.delete("/{customer_id}")
def delete_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    label = label_of(db, Customer, customer_id, "email") or label_of(db, Customer, customer_id, "first_name")
    deleted = CustomerService.delete_customer(db, customer_id)

    if not deleted:
        raise NotFound("Customer")

    record_audit(db, _admin["username"], "customer.delete", "customer", customer_id, {"label": label})

    return {"message": "Customer deleted successfully"}
