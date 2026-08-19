from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.dependencies import require_admin
from app.customers.model import CustomerCreate, CustomerUpdate, CustomerRead, CustomerListResponse
from app.customers.service import CustomerService
import math

router = APIRouter(prefix="/customers", tags=["Customers"])


@router.post("/", response_model=CustomerRead)
def create_customer(
    customer: CustomerCreate,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    return CustomerService.create_customer(db, customer)


@router.get("/", response_model=CustomerListResponse)
def get_customers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    items, total = CustomerService.get_all_customers(
        db, page=page, page_size=page_size, search=search
    )
    total_pages = math.ceil(total / page_size) if page_size else 0
    return CustomerListResponse(
        items=items, total=total, page=page, page_size=page_size, total_pages=total_pages
    )


@router.get("/{customer_id}", response_model=CustomerRead)
def get_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    customer = CustomerService.get_customer_by_id(db, customer_id)

    if not customer:
        raise HTTPException(404, "Customer not found")

    return customer


@router.put("/{customer_id}", response_model=CustomerRead)
def update_customer(
    customer_id: int,
    update: CustomerUpdate,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    updated = CustomerService.update_customer(db, customer_id, update)

    if not updated:
        raise HTTPException(404, "Customer not found")

    return updated


@router.delete("/{customer_id}")
def delete_customer(
    customer_id: int,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    deleted = CustomerService.delete_customer(db, customer_id)

    if not deleted:
        raise HTTPException(404, "Customer not found")

    return {"message": "Customer deleted successfully"}
