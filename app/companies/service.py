from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from app.entities import Company, Customer, Project, Invoice
from app.companies.model import CompanyStats, CompanyProfile


class CompanyService:

    @staticmethod
    def create_company(db: Session, company):
        new_company = Company(
            name=company.name,
            billing_email=company.billing_email,
            phone=company.phone,
            billing_address=company.billing_address,
            payment_terms_days=company.payment_terms_days,
            credit_limit=company.credit_limit,
            notes=company.notes,
        )
        try:
            db.add(new_company)
            db.commit()
            db.refresh(new_company)
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=400, detail="Duplicate company data")
        return new_company

    @staticmethod
    def get_all_companies(db: Session, page: int = 1, page_size: int = 20, search: str | None = None):
        query = db.query(Company)

        if search:
            like = f"%{search}%"
            query = query.filter(
                or_(
                    Company.name.ilike(like),
                    Company.billing_email.ilike(like),
                    Company.phone.ilike(like),
                )
            )

        total = query.count()
        items = (
            query.order_by(Company.name)
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )
        return items, total

    @staticmethod
    def get_company_by_id(db: Session, company_id: int):
        return db.get(Company, company_id)

    # Mirrors CustomerService.get_customer_profile's exact aggregate-query
    # shapes, just scoped to every contact (Customer.company_id == this
    # company) via customer_ids.in_(...) instead of a single customer_id.
    @staticmethod
    def get_company_profile(db: Session, company_id: int) -> CompanyProfile | None:
        company = db.get(Company, company_id)
        if not company:
            return None

        # A company's own contact list is naturally small (unlike a single
        # customer's orders/invoices) - capped at 500 same as
        # get_customer_profile's lists, not paginated.
        contacts = (
            db.query(Customer)
            .filter(Customer.company_id == company_id)
            .order_by(Customer.first_name, Customer.last_name)
            .limit(500)
            .all()
        )
        customer_ids = [c.id for c in contacts]

        if not customer_ids:
            return CompanyProfile(
                company=company,
                stats=CompanyStats(
                    total_contacts=0,
                    total_orders=0,
                    active_orders=0,
                    total_spent=0.0,
                    outstanding_balance=0.0,
                    total_invoices=0,
                    pending_invoices=0,
                ),
                contacts=contacts,
            )

        total_orders = (
            db.query(func.count(Project.id))
            .filter(Project.customer_id.in_(customer_ids))
            .scalar()
            or 0
        )
        active_orders = (
            db.query(func.count(Project.id))
            .filter(Project.customer_id.in_(customer_ids), Project.delivered_at.is_(None))
            .scalar()
            or 0
        )
        total_spent = round(
            db.query(func.coalesce(func.sum(Invoice.amount), 0.0))
            .join(Project, Invoice.project_id == Project.id)
            .filter(Project.customer_id.in_(customer_ids), Invoice.status == "paid")
            .scalar()
            or 0.0,
            2,
        )
        pending_amounts = (
            db.query(Invoice.amount, Invoice.advance_amount)
            .join(Project, Invoice.project_id == Project.id)
            .filter(Project.customer_id.in_(customer_ids), Invoice.status == "pending")
            .all()
        )
        outstanding_balance = round(
            sum(max(0.0, amount - (advance or 0.0)) for amount, advance in pending_amounts), 2
        )
        total_invoices = (
            db.query(func.count(Invoice.id))
            .join(Project, Invoice.project_id == Project.id)
            .filter(Project.customer_id.in_(customer_ids))
            .scalar()
            or 0
        )

        return CompanyProfile(
            company=company,
            stats=CompanyStats(
                total_contacts=len(contacts),
                total_orders=total_orders,
                active_orders=active_orders,
                total_spent=total_spent,
                outstanding_balance=outstanding_balance,
                total_invoices=total_invoices,
                pending_invoices=len(pending_amounts),
            ),
            contacts=contacts,
        )

    @staticmethod
    def update_company(db: Session, company_id: int, update):
        company = db.get(Company, company_id)
        if not company:
            return None
        for key, value in update.dict(exclude_unset=True).items():
            setattr(company, key, value)
        try:
            db.commit()
            db.refresh(company)
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=400, detail="Duplicate company data")
        return company

    @staticmethod
    def delete_company(db: Session, company_id: int) -> bool:
        company = db.get(Company, company_id)
        if not company:
            return False
        db.delete(company)  # ON DELETE SET NULL detaches contacts, doesn't delete them
        db.commit()
        return True
