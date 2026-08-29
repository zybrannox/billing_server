from datetime import datetime
from sqlalchemy import case, or_
from sqlalchemy.orm import Session, joinedload, selectinload
from app.entities.project import Project
from app.entities.customer import Customer
from .model import ProjectCreate, ProjectUpdate


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
):
    query = db.query(Project).options(
        joinedload(Project.customer), selectinload(Project.files)
    )

    if search:
        like = f"%{search}%"
        query = query.outerjoin(Customer, Project.customer_id == Customer.id).filter(
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

    if db_project.print_completed_at is None:
        db_project.print_completed_at = datetime.utcnow()
        db_project.print_completed_by = username
        db_project.print_status = "Completed"
        db.commit()
        db.refresh(db_project)

    return db_project


def mark_delivered(db: Session, project_id: int, username: str):
    """Idempotent, same reasoning as mark_design_completed."""
    db_project = get_project(db, project_id)
    if not db_project:
        return None

    if db_project.delivered_at is None:
        db_project.delivered_at = datetime.utcnow()
        db_project.delivered_by = username
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
