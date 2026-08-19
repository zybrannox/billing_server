from sqlalchemy.orm import Session
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from app.entities import Customer


class CustomerService:

    @staticmethod
    def create_customer(db: Session, customer):
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

        total = query.count()

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
