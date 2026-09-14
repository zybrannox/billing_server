from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.dependencies import require_admin, get_current_user
from app.invoices.model import InvoiceRead
from .model import (
    QuotationCreate,
    QuotationDetailRead,
    QuotationListResponse,
    QuotationStatusUpdate,
    QuotationConvertRequest,
)
from .service import (
    service_create,
    service_list,
    service_get_details,
    service_update_status,
    service_convert,
    service_delete,
)

router = APIRouter(prefix="/quotations", tags=["Quotations"])

# Same authorization shape as invoices (see app/invoices/controller.py):
# create/details/status/convert are open to any authenticated user since
# raising and following up on a quotation is normal day-to-day work for
# any role, not a financial-oversight action. Only the full cross-customer
# list and hard delete stay admin-only.


@router.post("/", response_model=QuotationDetailRead)
def create(payload: QuotationCreate, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    quotation = service_create(db, payload)
    return service_get_details(db, quotation.id)


@router.get("/", response_model=QuotationListResponse)
def list_quotations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    customer_id: int | None = Query(None),
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    return service_list(db, page=page, page_size=page_size, search=search, customer_id=customer_id)


@router.get("/{quotation_id}/details", response_model=QuotationDetailRead)
def get_quotation_details(quotation_id: int, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    return service_get_details(db, quotation_id)


@router.patch("/{quotation_id}/status", response_model=QuotationDetailRead)
def update_status(
    quotation_id: int,
    payload: QuotationStatusUpdate,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    return service_update_status(db, quotation_id, payload.status)


@router.post("/{quotation_id}/convert", response_model=InvoiceRead)
def convert_to_invoice(
    quotation_id: int,
    payload: QuotationConvertRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return service_convert(db, quotation_id, payload, current_user["username"])


@router.delete("/{quotation_id}")
def delete_quotation(quotation_id: int, db: Session = Depends(get_db), _admin: dict = Depends(require_admin)):
    return service_delete(db, quotation_id)
