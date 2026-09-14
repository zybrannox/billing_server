from datetime import datetime
from sqlalchemy.orm import Session, joinedload
from app.entities.quotation import Quotation
from app.entities.quotation_item import QuotationItem
from app.entities.customer import Customer
from app.entities.project import Project
from app.entities.invoice import Invoice
from app.entities.invoice_item import InvoiceItem
from .calculations import compute_line
from .model import QuotationCreate, QuotationConvertRequest


def get_customer(db: Session, customer_id: int):
    return db.query(Customer).filter(Customer.id == customer_id).first()


def create_quotation(db: Session, payload: QuotationCreate):
    try:
        new_quotation = Quotation(
            customer_id=payload.customer_id,
            project_type=payload.project_type,
            valid_until=payload.valid_until,
            status="pending",
            subtotal=0,  # set below once items are totaled
            discount_amount=payload.discount_amount,
            amount=0,
        )
        db.add(new_quotation)
        db.flush()  # assigns new_quotation.id without committing yet

        subtotal = 0.0
        for idx, item in enumerate(payload.items):
            sq_ft, line_total = compute_line(item.width, item.height, item.rate, item.pieces, item.unit)
            subtotal += line_total
            db.add(
                QuotationItem(
                    quotation_id=new_quotation.id,
                    description=item.description,
                    width=item.width,
                    height=item.height,
                    unit=item.unit,
                    sq_ft=sq_ft,
                    rate=item.rate,
                    pieces=item.pieces,
                    total=line_total,
                    is_manual_total=item.is_manual_total,
                    sort_order=idx,
                )
            )

        new_quotation.subtotal = round(subtotal, 2)
        new_quotation.amount = round(new_quotation.subtotal - new_quotation.discount_amount, 2)
        year = (new_quotation.created_at or datetime.utcnow()).year
        new_quotation.quotation_number = f"QUOTE-{year}-{new_quotation.id:05d}"

        db.commit()
        db.refresh(new_quotation)
        return new_quotation
    except Exception as e:
        db.rollback()
        print(f"ERROR creating quotation: {e}")
        raise e


def get_quotation(db: Session, quotation_id: int):
    return (
        db.query(Quotation)
        .options(joinedload(Quotation.items), joinedload(Quotation.customer))
        .filter(Quotation.id == quotation_id)
        .first()
    )


def get_all_quotations(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    customer_id: int | None = None,
):
    query = db.query(Quotation).options(joinedload(Quotation.customer))

    if search or customer_id:
        query = query.outerjoin(Customer, Quotation.customer_id == Customer.id)

    if search:
        like = f"%{search}%"
        query = query.filter(
            Quotation.quotation_number.ilike(like)
            | Quotation.project_type.ilike(like)
            | Customer.first_name.ilike(like)
            | Customer.last_name.ilike(like)
        )

    if customer_id:
        query = query.filter(Quotation.customer_id == customer_id)

    query = query.order_by(Quotation.created_at.desc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return items, total


def update_quotation_status(db: Session, quotation_id: int, status: str):
    quotation = get_quotation(db, quotation_id)
    if not quotation:
        return None
    quotation.status = status
    db.commit()
    db.refresh(quotation)
    return quotation


def delete_quotation(db: Session, quotation_id: int):
    quotation = get_quotation(db, quotation_id)
    if not quotation:
        return False
    db.delete(quotation)
    db.commit()
    return True


def convert_quotation_to_invoice(
    db: Session, quotation: Quotation, payload: QuotationConvertRequest, username: str
):
    """Turns an accepted quotation into a real Project + Invoice, carrying
    its customer/job-type/items/discount straight over - the only new
    information needed is what the quotation never asked for (who does the
    work, when - see QuotationConvertRequest). Both rows are created and
    the quotation is marked converted in one transaction: a failure partway
    through must not leave a Project with no Invoice, or a quotation that
    silently lost its items to a project that doesn't exist.
    """
    try:
        new_project = Project(
            project_type=quotation.project_type,
            assigned_to=payload.assigned_to,
            priority=payload.priority,
            client_status=payload.client_status,
            print_status="In Progress",
            start_date=payload.start_date,
            delivery_date=payload.delivery_date,
            customer_id=quotation.customer_id,
        )
        db.add(new_project)
        db.flush()  # assigns new_project.id

        # The quotation was already effectively "designed" - its line items
        # are real dimensions/rates the customer already agreed to, not a
        # pending design task - so the invoice can be raised immediately,
        # same as the ordinary "Mark Design Completed" -> Generate Invoice
        # flow, just skipping straight to the point that flow ends at.
        new_project.design_completed_at = datetime.utcnow()
        new_project.design_completed_by = username

        new_invoice = Invoice(
            project_id=new_project.id,
            status="pending",
            subtotal=quotation.subtotal,
            discount_amount=quotation.discount_amount,
            amount=quotation.amount,
            advance_amount=0,
        )
        db.add(new_invoice)
        db.flush()  # assigns new_invoice.id

        for item in quotation.items:
            db.add(
                InvoiceItem(
                    invoice_id=new_invoice.id,
                    description=item.description,
                    width=item.width,
                    height=item.height,
                    unit=item.unit,
                    sq_ft=item.sq_ft,
                    rate=item.rate,
                    pieces=item.pieces,
                    total=item.total,
                    is_manual_total=item.is_manual_total,
                    sort_order=item.sort_order,
                )
            )

        year = (new_invoice.created_at or datetime.utcnow()).year
        new_invoice.invoice_number = f"INV-{year}-{new_invoice.id:05d}"

        quotation.status = "converted"
        quotation.converted_project_id = new_project.id
        quotation.converted_invoice_id = new_invoice.id

        db.commit()
        db.refresh(new_invoice)
        return new_invoice
    except Exception as e:
        db.rollback()
        print(f"ERROR converting quotation {quotation.id} to invoice: {e}")
        raise e
