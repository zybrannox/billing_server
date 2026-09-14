from datetime import datetime
from sqlalchemy import case
from sqlalchemy.orm import Session, joinedload
from app.entities.invoice import Invoice
from app.entities.invoice_item import InvoiceItem
from app.entities.project import Project
from app.entities.customer import Customer
from .calculations import compute_line
from .model import InvoiceCreate, InvoiceUpdate

# Pending invoices - the ones that actually need someone's attention - sort
# first regardless of when they were raised; paid/cancelled (nothing left
# to do) fall in behind. Mirrors app/projects/repository.py's
# _PRINT_STATUS_RANK/_PRIORITY_RANK pattern for the same reason: what needs
# action belongs at the top of the list, not buried by recency alone.
_INVOICE_STATUS_RANK = case(
    (Invoice.status == "pending", 1),
    (Invoice.status == "paid", 2),
    (Invoice.status == "cancelled", 3),
    else_=4,
)


def get_project_with_customer(db: Session, project_id: int):
    """Shared by the invoice-preview endpoint (before an invoice exists)
    and service_get_details (after one does) - both need the same
    project + its customer, if any."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return None, None
    customer = (
        db.query(Customer).filter(Customer.id == project.customer_id).first()
        if project.customer_id
        else None
    )
    return project, customer


def create_invoice(db: Session, payload: InvoiceCreate, username: str):
    try:
        # `new_project` (see InvoiceNewProject) means this invoice is being
        # raised for a job that has no Project row yet - create it here, in
        # the same transaction as the invoice below, so a failure partway
        # through can never leave an orphaned project with no invoice (or
        # an invoice with a project_id that doesn't exist). Not committed
        # until the whole function's final db.commit().
        project_id = payload.project_id
        if payload.new_project:
            now = datetime.utcnow()
            new_project = Project(
                project_type=payload.new_project.project_type,
                customer_id=payload.new_project.customer_id,
                # Not asked for on the invoice screen (see InvoiceNewProject)
                # - this project exists purely to hang the invoice off of,
                # not to be scheduled or assigned like ordinary tracked
                # work, so it's attributed to whoever raised the invoice
                # and dated/marked as already settled rather than left to
                # placeholder values that would read as real scheduling
                # decisions nobody actually made.
                assigned_to=username,
                priority="Normal",
                client_status="Confirmed",
                print_status="In Progress",
                start_date=now,
                delivery_date=now,
            )
            db.add(new_project)
            db.flush()  # assigns new_project.id
            # This job's dimensions/rates are already decided (they're
            # right here in the invoice being raised), not a pending design
            # task - so it goes straight to "designed", same as the ordinary
            # Mark Design Completed -> Generate Invoice flow, just skipping
            # to the point that flow ends at instead of needing a second
            # request to get there.
            new_project.design_completed_at = now
            new_project.design_completed_by = username
            project_id = new_project.id

        new_invoice = Invoice(
            project_id=project_id,
            due_date=payload.due_date,
            status="pending",
            subtotal=0,  # set below once items are totaled
            discount_amount=payload.discount_amount,
            amount=0,
            advance_amount=payload.advance_amount,
            payment_method=payload.payment_method,
            payment_reference=payload.payment_reference,
        )
        db.add(new_invoice)
        db.flush()  # assigns new_invoice.id without committing yet

        subtotal = 0.0
        for idx, item in enumerate(payload.items):
            # Rounded to cents/paise - avoids floating-point noise (e.g.
            # 3.33 * 3.33) showing up in a financial document.
            sq_ft, line_total = compute_line(item.width, item.height, item.rate, item.pieces, item.unit)
            subtotal += line_total
            db.add(
                InvoiceItem(
                    invoice_id=new_invoice.id,
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

        new_invoice.subtotal = round(subtotal, 2)
        # `amount` is the actual total owed after the discount - everything
        # downstream (balance_due, the Billing list) reads `amount`, never
        # `subtotal`.
        new_invoice.amount = round(new_invoice.subtotal - new_invoice.discount_amount, 2)
        # invoice_number depends on the row's own id, so it can only be
        # generated after the insert - format: INV-<year>-<id, zero-padded>.
        year = (new_invoice.created_at or datetime.utcnow()).year
        new_invoice.invoice_number = f"INV-{year}-{new_invoice.id:05d}"

        db.commit()
        db.refresh(new_invoice)
        return new_invoice
    except Exception as e:
        db.rollback()
        print(f"ERROR creating invoice: {e}")
        raise e

def get_latest_invoice_for_project(db: Session, project_id: int):
    """A project can end up with more than one invoice over time (a
    cancelled one re-invoiced, say) - the most recently created one is
    what actually matters for "has this order been paid for" checks (see
    service_get_project_payment_status), not the first one ever made."""
    return (
        db.query(Invoice)
        .filter(Invoice.project_id == project_id)
        .order_by(Invoice.created_at.desc())
        .first()
    )


def get_invoice(db: Session, invoice_id: int):
    return (
        db.query(Invoice)
        .options(
            joinedload(Invoice.items),
            # customer_name/project_type (see entities/invoice.py) walk
            # this same relationship chain - eager-load it here too so
            # reading one invoice's details doesn't fire it lazily.
            joinedload(Invoice.project).joinedload(Project.customer),
        )
        .filter(Invoice.id == invoice_id)
        .first()
    )

def get_all_invoices(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    customer_id: int | None = None,
):
    # Previously returned every invoice ever created, unpaginated - fine
    # with a handful of rows, but the response only grows over time (unlike
    # projects, invoices are never really "done" and cleared out), so this
    # was a slow-motion outage waiting for enough billing history to build
    # up. Matches the page/total_pages shape already used by
    # customers/projects.
    #
    # joinedload avoids an N+1: every row's customer_name/project_type
    # property (see entities/invoice.py) walks Invoice -> Project ->
    # Customer, which without this would fire two more queries *per row*
    # on every page load.
    query = db.query(Invoice).options(
        joinedload(Invoice.project).joinedload(Project.customer)
    )

    # Both branches below need the same Project/Customer join, so it's
    # done once here rather than risking two joins (or a missing one) if
    # search and customer_id are ever both passed at once.
    if search or customer_id:
        query = query.outerjoin(Project, Invoice.project_id == Project.id).outerjoin(
            Customer, Project.customer_id == Customer.id
        )

    if search:
        # Matches on the invoice number itself, or who/what it's for -
        # exactly the three things admins actually scan the list for (see
        # conversation: "hard to track who's invoice it is and for which
        # project it is").
        like = f"%{search}%"
        query = query.filter(
            Invoice.invoice_number.ilike(like)
            | Project.project_type.ilike(like)
            | Customer.first_name.ilike(like)
            | Customer.last_name.ilike(like)
        )

    if customer_id:
        query = query.filter(Project.customer_id == customer_id)

    query = query.order_by(_INVOICE_STATUS_RANK, Invoice.created_at.desc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return items, total

def update_invoice(db: Session, invoice_id: int, invoice: InvoiceUpdate):
    db_invoice = get_invoice(db, invoice_id)
    if not db_invoice:
        return None

    for key, value in invoice.model_dump(exclude_unset=True).items():
        setattr(db_invoice, key, value)

    db.commit()
    db.refresh(db_invoice)
    return db_invoice

def delete_invoice(db: Session, invoice_id: int):
    db_invoice = get_invoice(db, invoice_id)
    if not db_invoice:
        return False
    db.delete(db_invoice)
    db.commit()
    return True
