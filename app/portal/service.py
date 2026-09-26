from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.entities import Customer, Company
from app.projects import service as project_service
from app.invoices import service as invoice_service
from app.invoices.repository import get_invoice as get_invoice_raw
from .model import PortalProfile


class PortalService:
    """Every method takes the `client` dict from get_current_client
    ({customer_id, company_id, ...}) and decides "my own" vs "my whole
    company's" purely from whether company_id is set - see
    app/entities/customer.py, a company contact is just a Customer row
    with company_id set, no separate contact entity."""

    @staticmethod
    def get_profile(db: Session, client: dict) -> PortalProfile:
        customer = db.get(Customer, client["customer_id"])
        company = db.get(Company, customer.company_id) if customer.company_id else None
        return PortalProfile(
            customer_id=customer.id,
            first_name=customer.first_name,
            last_name=customer.last_name,
            email=customer.email,
            contact_number=customer.contact_number,
            company_id=customer.company_id,
            company_name=company.name if company else None,
        )

    @staticmethod
    def list_orders(db: Session, client: dict, page: int, page_size: int):
        if client["company_id"]:
            return project_service.service_list(
                db, page=page, page_size=page_size, company_id=client["company_id"]
            )
        return project_service.service_list(
            db, page=page, page_size=page_size, customer_id=client["customer_id"]
        )

    @staticmethod
    def _owns_project(client: dict, project) -> bool:
        if project.customer_id == client["customer_id"]:
            return True
        if client["company_id"] and project.customer and project.customer.company_id == client["company_id"]:
            return True
        return False

    @staticmethod
    def get_order(db: Session, client: dict, project_id: int):
        project = project_service.service_get(db, project_id)
        # 404, not 403 - an out-of-scope id shouldn't confirm to the caller
        # that it exists at all.
        if not PortalService._owns_project(client, project):
            raise HTTPException(status_code=404, detail="Order not found")
        return project

    @staticmethod
    def list_invoices(db: Session, client: dict, page: int, page_size: int):
        if client["company_id"]:
            return invoice_service.service_list(
                db, page=page, page_size=page_size, company_id=client["company_id"]
            )
        return invoice_service.service_list(
            db, page=page, page_size=page_size, customer_id=client["customer_id"]
        )

    @staticmethod
    def get_invoice(db: Session, client: dict, invoice_id: int):
        invoice = get_invoice_raw(db, invoice_id)
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")

        project = invoice.project
        owns = bool(project) and (
            project.customer_id == client["customer_id"]
            or (client["company_id"] and project.customer and project.customer.company_id == client["company_id"])
        )
        if not owns:
            raise HTTPException(status_code=404, detail="Invoice not found")

        return invoice_service.service_get_details(db, invoice_id)
