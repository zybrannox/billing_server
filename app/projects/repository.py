from datetime import datetime, timedelta
from sqlalchemy import case, or_
from sqlalchemy.orm import Session, joinedload, selectinload
from app.entities.project import Project
from app.entities.customer import Customer
from .model import ProjectCreate, ProjectUpdate

# How long a fully-delivered project stays on the admin "Ongoing Activities"
# board before rolling off to the (unfiltered) Project History page - see
# get_all_projects' `view="ongoing"` branch below.
ONGOING_VIEW_RETENTION_DAYS = 7


def create_project(db: Session, project: ProjectCreate):
    new_project = Project(**project.dict())
    db.add(new_project)
    db.commit()
    db.refresh(new_project)
    return new_project


def get_project(db: Session, project_id: int):
    return (
        db.query(Project)
        .options(joinedload(Project.customer), joinedload(Project.files))
        .filter(Project.id == project_id)
        .first()
    )


# Default table order: Pending -> In Progress -> Completed, and within each
# status Urgent -> High -> Normal -> Low (Low always sorts last within its
# status group rather than being hidden).
_PRINT_STATUS_RANK = case(
    (Project.print_status == "Pending", 1),
    (Project.print_status == "In Progress", 2),
    (Project.print_status == "Completed", 3),
    else_=4,
)
_PRIORITY_RANK = case(
    (Project.priority == "Urgent", 1),
    (Project.priority == "High", 2),
    (Project.priority == "Normal", 3),
    (Project.priority == "Low", 4),
    else_=5,
)


def get_all_projects(
    db: Session,
    page: int = 1,
    page_size: int = 10,
    search: str | None = None,
    print_status: str | None = None,
    priority: str | None = None,
    customer_id: int | None = None,
    project_id: int | None = None,
    assigned_to: str | None = None,
    company_id: int | None = None,
    # Opt-in only - every other caller (customer/employee profile pulls, the
    # client portal's "my orders", the invoice-creation project picker,
    # /projects/billing) leaves this unset and keeps seeing everything,
    # exactly as before. Only the admin "Ongoing Activities" page passes
    # "ongoing" (see app/projects/controller.py).
    view: str | None = None,
):
    query = db.query(Project).options(
        joinedload(Project.customer), selectinload(Project.files)
    )

    if view == "ongoing":
        # Roll a project off the ongoing board once it's both fully
        # delivered (delivered_at set - matches the same "still active"
        # check already used in app/customers/service.py and
        # app/users/service.py) AND old enough (created more than
        # ONGOING_VIEW_RETENTION_DAYS ago). Anything still in progress stays
        # visible indefinitely, no matter its age - only finished work moves
        # to Project History.
        stale_cutoff = datetime.utcnow() - timedelta(days=ONGOING_VIEW_RETENTION_DAYS)
        query = query.filter(
            or_(
                Project.delivered_at.is_(None),
                Project.created_at > stale_cutoff,
            )
        )

    # Both branches below need the same Project -> Customer join, so it's
    # done once here rather than joining twice if search and company_id are
    # ever both passed at once - mirrors get_all_invoices' identical guard
    # (app/invoices/repository.py).
    if search or company_id:
        query = query.outerjoin(Customer, Project.customer_id == Customer.id)

    # Every project belonging to any contact of this company - powers the
    # client portal's company-wide "my orders" view (see app/portal).
    if company_id:
        query = query.filter(Customer.company_id == company_id)

    # Jumping straight to one known project (e.g. from a dashboard/
    # notification row) - an exact id match, so it deliberately bypasses
    # every other filter below rather than being ANDed with them.
    if project_id:
        query = query.filter(Project.id == project_id)

    # Exact match, not ilike - assigned_to is always set from a real
    # username (see AddProject's employee picker), never free text, so a
    # partial/case-insensitive match would only risk pulling in the wrong
    # employee's work.
    if assigned_to:
        query = query.filter(Project.assigned_to == assigned_to)

    if search:
        like = f"%{search}%"
        query = query.filter(
            or_(
                Project.project_type.ilike(like),
                Project.assigned_to.ilike(like),
                Project.description.ilike(like),
                Customer.first_name.ilike(like),
                Customer.last_name.ilike(like),
                (Customer.first_name + " " + Customer.last_name).ilike(like),
            )
        )

    if print_status:
        query = query.filter(Project.print_status == print_status)

    if priority:
        query = query.filter(Project.priority == priority)

    if customer_id:
        query = query.filter(Project.customer_id == customer_id)

    total = query.count()

    items = (
        # Pinned projects always float to the top, ahead of the usual
        # status/priority ordering - a real sort key (not a client-side
        # reorder-after-fetch), so it stays correct across pages instead of
        # only pinning-to-the-top-of-whatever-page-you're-on.
        query.order_by(Project.pinned.desc(), _PRINT_STATUS_RANK, _PRIORITY_RANK, Project.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return items, total



def update_project(db: Session, project_id: int, project: ProjectUpdate):
    db_project = get_project(db, project_id)
    if not db_project:  
        return None
    
    for key, value in project.dict(exclude_unset=True).items():
        setattr(db_project, key, value)

    db.commit()
    db.refresh(db_project)
    return db_project


def mark_design_completed(db: Session, project_id: int, username: str):
    """Idempotent: a second call is a harmless no-op rather than clobbering
    the original timestamp/actor, so a double-click or retry can't corrupt
    the audit trail."""
    db_project = get_project(db, project_id)
    if not db_project:
        return None

    if db_project.design_completed_at is None:
        db_project.design_completed_at = datetime.utcnow()
        db_project.design_completed_by = username
        db.commit()
        db.refresh(db_project)

    return db_project


def mark_print_completed(db: Session, project_id: int, username: str):
    """Idempotent, same reasoning as mark_design_completed. Also flips
    print_status to Completed - the caller (service_mark_print_completed)
    has already checked design_completed_at is set, same rule the generic
    update path enforces for this same transition."""
    db_project = get_project(db, project_id)
    if not db_project:
        return None

    changed = False
    if db_project.print_completed_at is None:
        db_project.print_completed_at = datetime.utcnow()
        db_project.print_completed_by = username
        changed = True

    # Keep the status consistent even for legacy rows that already have an
    # audit timestamp but were never moved out of the in-progress state.
    if db_project.print_status != "Completed":
        db_project.print_status = "Completed"
        changed = True

    if changed:
        db.commit()
        db.refresh(db_project)

    return db_project


def mark_delivered(db: Session, project_id: int, username: str, on_credit: bool = False):
    """Idempotent, same reasoning as mark_design_completed. `on_credit` is
    only meaningful on the transition itself (delivered_at was still null)
    - an already-delivered project's on-credit flag is a historical fact
    about how that delivery actually happened, not something a repeat call
    should be able to flip after the fact."""
    db_project = get_project(db, project_id)
    if not db_project:
        return None

    if db_project.delivered_at is None:
        db_project.delivered_at = datetime.utcnow()
        db_project.delivered_by = username
        db_project.delivered_on_credit = on_credit
        db.commit()
        db.refresh(db_project)

    return db_project


def mark_notified(db: Session, project_id: int, username: str):
    """Not idempotent-gated like mark_design_completed/mark_delivered above -
    staff may re-notify a client (e.g. after a mistake), so this always
    overwrites with the latest notify, a "last notified" fact rather than a
    one-time milestone."""
    db_project = get_project(db, project_id)
    if not db_project:
        return None

    db_project.notified_at = datetime.utcnow()
    db_project.notified_by = username
    db.commit()
    db.refresh(db_project)
    return db_project


def toggle_pin(db: Session, project_id: int):
    """Flips pinned on/off - unlike the milestone marks above, pinning is a
    genuine two-way toggle (a user can freely pin/unpin), not a one-time
    audited transition, so there's no separate `by`/`at` pair to preserve."""
    db_project = get_project(db, project_id)
    if not db_project:
        return None

    db_project.pinned = not db_project.pinned
    db.commit()
    db.refresh(db_project)
    return db_project


def delete_project(db: Session, project_id: int):
    db_project = get_project(db, project_id)
    if not db_project:
        return None

    db.delete(db_project)
    db.commit()
    return True

def delete_projects(db: Session, project_ids: list[int]):
    projects = db.query(Project).filter(Project.id.in_(project_ids)).all()
    for project in projects:
        db.delete(project)
    db.commit()
    return projects
