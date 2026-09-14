from sqlalchemy.orm import Session
from sqlalchemy import select, or_, func
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from app.entities import Customer, Project, Invoice
from app.projects.repository import get_all_projects
from app.invoices.repository import get_all_invoices
from app.quotations.repository import get_all_quotations
from app.customers.model import CustomerStats, CustomerProfile


class CustomerService:

    @staticmethod
    def create_customer(db: Session, customer):
        if customer.email:
            exists = db.execute(
                select(Customer).where(Customer.email == customer.email)
            ).scalar_one_or_none()

            if exists:
                raise HTTPException(status_code=400, detail="Email already registered")

        new_customer = Customer(
            first_name=customer.first_name,
            last_name=customer.last_name,
            contact_number=customer.contact_number,
            email=customer.email,
        )

        try:
            db.add(new_customer)
            db.commit()
            db.refresh(new_customer)
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=400, detail="Duplicate customer data")

        return new_customer

    @staticmethod
    def get_all_customers(
        db: Session,
        page: int = 1,
        page_size: int = 20,
        search: str | None = None,
        sort: str = "name",
    ):
        # Always paginated - both the admin Customers table and the Add
        # Project search dropdown call this with a small page_size, so
        # neither ever pulls the full customer table into memory/network.
        query = db.query(Customer)

        if search:
            like = f"%{search}%"
            query = query.filter(
                or_(
                    Customer.first_name.ilike(like),
                    Customer.last_name.ilike(like),
                    Customer.email.ilike(like),
                    Customer.contact_number.ilike(like),
                )
            )

        # Total distinct matching customers - computed before any join, since
        # the "most_used" branch's outer join to Project only multiplies rows
        # per project (for the GROUP BY below), it doesn't change which or how
        # many customers match the search filter above.
        total = query.count()

        if sort == "most_used":
            # Surface customers with the most existing projects first, so the
            # Add Project dropdown lets users click a frequent customer
            # instead of hunting through an alphabetical list. Opt-in only -
            # every other caller (admin Customers table, project filters,
            # etc.) keeps the default alphabetical order untouched.
            project_count = func.count(Project.id)
            rows = (
                query.outerjoin(Project, Project.customer_id == Customer.id)
                .add_columns(project_count.label("project_count"))
                .group_by(Customer.id)
                .order_by(project_count.desc(), Customer.first_name, Customer.last_name)
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            items = [row[0] for row in rows]
        else:
            items = (
                query.order_by(Customer.first_name, Customer.last_name)
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )

        CustomerService._attach_payment_status(db, items)

        return items, total

    # Decorates each Customer ORM instance with a transient (never
    # persisted - db.commit()/flush() is never called here) payment_status/
    # outstanding_balance pair so the admin Customers table can show who
    # still owes money at a glance, without the frontend having to open
    # each customer's profile just to find out. One extra query for the
    # whole page rather than one per row.
    @staticmethod
    def _attach_payment_status(db: Session, customers: list[Customer]) -> None:
        if not customers:
            return

        ids = [c.id for c in customers]
        pending_invoices = (
            db.query(Invoice, Project.customer_id)
            .join(Project, Invoice.project_id == Project.id)
            .filter(Project.customer_id.in_(ids), Invoice.status == "pending")
            .all()
        )
        outstanding_by_customer: dict[int, float] = {}
        for invoice, customer_id in pending_invoices:
            outstanding_by_customer[customer_id] = (
                outstanding_by_customer.get(customer_id, 0.0) + invoice.balance_due
            )

        # "paid" needs positive evidence money actually changed hands - a
        # customer whose only invoice was cancelled has no outstanding
        # balance either, but was never actually paid, so checking "any
        # invoice at all" here previously mislabeled them "paid" too.
        paid_customer_ids = {
            row[0]
            for row in db.query(Project.customer_id)
            .join(Invoice, Invoice.project_id == Project.id)
            .filter(Project.customer_id.in_(ids), Invoice.status == "paid")
            .distinct()
            .all()
        }

        for customer in customers:
            outstanding = round(outstanding_by_customer.get(customer.id, 0.0), 2)
            customer.outstanding_balance = outstanding
            if outstanding > 0:
                customer.payment_status = "pending"
            elif customer.id in paid_customer_ids:
                customer.payment_status = "paid"
            else:
                customer.payment_status = "no_invoices"

    @staticmethod
    def get_customer_by_id(db: Session, customer_id: int):
        return db.get(Customer, customer_id)

    # One call for the whole profile page (see CustomerProfile) - customer
    # identity, every order, every invoice, and the summary numbers -
    # instead of the frontend firing three separate requests. page_size is
    # deliberately generous rather than paginated: a single customer's own
    # order/invoice history is small enough to show in full on their own
    # profile page, unlike the admin-wide Projects/Billing lists this data
    # is drawn from. Note that's about display only - the stats below are
    # computed via their own unbounded aggregate queries, not by reducing
    # these capped lists, so a customer who ever does cross 500 projects/
    # invoices in real usage gets a display list that's (reasonably) capped
    # rather than paginated, without the summary numbers above it silently
    # under-reporting to match.
    @staticmethod
    def get_customer_profile(db: Session, customer_id: int) -> CustomerProfile | None:
        customer = db.get(Customer, customer_id)
        if not customer:
            return None

        projects, _ = get_all_projects(db, page=1, page_size=500, customer_id=customer_id)
        invoices, _ = get_all_invoices(db, page=1, page_size=500, customer_id=customer_id)
        quotations, _ = get_all_quotations(db, page=1, page_size=500, customer_id=customer_id)

        total_orders = (
            db.query(func.count(Project.id)).filter(Project.customer_id == customer_id).scalar() or 0
        )
        active_orders = (
            db.query(func.count(Project.id))
            .filter(Project.customer_id == customer_id, Project.delivered_at.is_(None))
            .scalar()
            or 0
        )
        total_spent = round(
            db.query(func.coalesce(func.sum(Invoice.amount), 0.0))
            .join(Project, Invoice.project_id == Project.id)
            .filter(Project.customer_id == customer_id, Invoice.status == "paid")
            .scalar()
            or 0.0,
            2,
        )
        pending_amounts = (
            db.query(Invoice.amount, Invoice.advance_amount)
            .join(Project, Invoice.project_id == Project.id)
            .filter(Project.customer_id == customer_id, Invoice.status == "pending")
            .all()
        )
        outstanding_balance = round(
            sum(max(0.0, amount - (advance or 0.0)) for amount, advance in pending_amounts), 2
        )
        pending_invoices = len(pending_amounts)

        return CustomerProfile(
            customer=customer,
            stats=CustomerStats(
                total_orders=total_orders,
                active_orders=active_orders,
                total_spent=total_spent,
                outstanding_balance=outstanding_balance,
                pending_invoices=pending_invoices,
            ),
            projects=projects,
            invoices=invoices,
            quotations=quotations,
        )

    @staticmethod
    def update_customer(db: Session, customer_id: int, update):
        customer = db.get(Customer, customer_id)
        if not customer:
            return None

        for key, value in update.dict(exclude_unset=True).items():
            setattr(customer, key, value)

        try:
            db.commit()
            db.refresh(customer)
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=400, detail="Duplicate customer data")

        return customer

    @staticmethod
    def delete_customer(db: Session, customer_id: int) -> bool:
        customer = db.get(Customer, customer_id)
        if not customer:
            return False
        db.delete(customer)
        db.commit()
        return True
