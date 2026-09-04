from sqlalchemy.orm import Session
from sqlalchemy import select, or_, func
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from app.entities import Customer, Project


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

        return items, total

    @staticmethod
    def get_customer_by_id(db: Session, customer_id: int):
        return db.get(Customer, customer_id)

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
