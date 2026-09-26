from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.client_auth.dependencies import get_current_client
from app.projects.model import ProjectRead, ProjectListResponse
from app.invoices.model import InvoiceListResponse, InvoiceDetailRead
from .model import PortalProfile
from .service import PortalService

router = APIRouter(prefix="/portal", tags=["Portal"])


@router.get("/me", response_model=PortalProfile)
def get_profile(db: Session = Depends(get_db), client: dict = Depends(get_current_client)):
    return PortalService.get_profile(db, client)


@router.get("/orders", response_model=ProjectListResponse)
def list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    client: dict = Depends(get_current_client),
):
    return PortalService.list_orders(db, client, page, page_size)


@router.get("/orders/{project_id}", response_model=ProjectRead)
def get_order(project_id: int, db: Session = Depends(get_db), client: dict = Depends(get_current_client)):
    return PortalService.get_order(db, client, project_id)


@router.get("/invoices", response_model=InvoiceListResponse)
def list_invoices(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    client: dict = Depends(get_current_client),
):
    return PortalService.list_invoices(db, client, page, page_size)


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetailRead)
def get_invoice(invoice_id: int, db: Session = Depends(get_db), client: dict = Depends(get_current_client)):
    return PortalService.get_invoice(db, client, invoice_id)
