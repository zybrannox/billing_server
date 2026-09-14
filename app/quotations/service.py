import math
from sqlalchemy.orm import Session
from fastapi import HTTPException
from .calculations import compute_quotation_total
from .repository import (
    create_quotation,
    get_customer,
    get_quotation,
    get_all_quotations,
    update_quotation_status,
    delete_quotation,
    convert_quotation_to_invoice,
)
from .model import QuotationCreate, QuotationListResponse, QuotationConvertRequest


def service_create(db: Session, payload: QuotationCreate):
    customer = get_customer(db, payload.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    subtotal = compute_quotation_total(payload.items)

    if payload.discount_amount > subtotal:
        raise HTTPException(
            status_code=400,
            detail="Discount can't exceed the quotation subtotal",
        )

    return create_quotation(db, payload)


def service_list(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    customer_id: int | None = None,
) -> QuotationListResponse:
    items, total = get_all_quotations(db, page=page, page_size=page_size, search=search, customer_id=customer_id)
    total_pages = math.ceil(total / page_size) if page_size else 0
    return QuotationListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


def _quotation_detail_dict(quotation):
    return {
        "id": quotation.id,
        "quotation_number": quotation.quotation_number,
        "customer_id": quotation.customer_id,
        "project_type": quotation.project_type,
        "subtotal": quotation.subtotal,
        "discount_amount": quotation.discount_amount,
        "amount": quotation.amount,
        "status": quotation.status,
        "valid_until": quotation.valid_until,
        "created_at": quotation.created_at,
        "converted_project_id": quotation.converted_project_id,
        "converted_invoice_id": quotation.converted_invoice_id,
        "customer_name": quotation.customer_name,
        "customer": quotation.customer,
        "items": quotation.items,
    }


def service_get_details(db: Session, quotation_id: int):
    quotation = get_quotation(db, quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")
    return _quotation_detail_dict(quotation)


def service_update_status(db: Session, quotation_id: int, status: str):
    quotation = get_quotation(db, quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")

    if quotation.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"This quotation is already {quotation.status} - its status can't be changed.",
        )

    updated = update_quotation_status(db, quotation_id, status)
    return _quotation_detail_dict(updated)


def service_convert(db: Session, quotation_id: int, payload: QuotationConvertRequest, username: str):
    quotation = get_quotation(db, quotation_id)
    if not quotation:
        raise HTTPException(status_code=404, detail="Quotation not found")

    if quotation.status != "accepted":
        raise HTTPException(
            status_code=400,
            detail=f"Only an accepted quotation can be converted to an invoice (this one is {quotation.status}).",
        )

    return convert_quotation_to_invoice(db, quotation, payload, username)


def service_delete(db: Session, quotation_id: int):
    success = delete_quotation(db, quotation_id)
    if not success:
        raise HTTPException(status_code=404, detail="Quotation not found")
    return {"message": "Quotation deleted successfully"}
