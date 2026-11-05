from app.pagination import page_count
from sqlalchemy.orm import Session, selectinload
from fastapi import HTTPException
from app.errors import NotFound
from app.entities.project import Project
from app.invoices.repository import get_latest_invoice_for_project
from .repository import (
    create_project,
    get_project,
    get_all_projects,
    update_project,
    mark_design_completed,
    mark_print_completed,
    mark_delivered,
    mark_notified,
    toggle_pin,
)
from .model import ProjectCreate, ProjectUpdate, ProjectListResponse
from app.bin.service import BinEntry, move_to_bin


def service_create(db: Session, payload: ProjectCreate):
    return create_project(db, payload)


def service_get(db: Session, project_id: int):
    result = get_project(db, project_id)
    if not result:
        raise NotFound("Project")
    return result


def service_list(
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
    view: str | None = None,
    order: str | None = None,
) -> ProjectListResponse:
    items, total = get_all_projects(
        db,
        page=page,
        page_size=page_size,
        search=search,
        print_status=print_status,
        priority=priority,
        customer_id=customer_id,
        project_id=project_id,
        assigned_to=assigned_to,
        company_id=company_id,
        view=view,
        order=order,
    )
    total_pages = page_count(total, page_size)
    return ProjectListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


def service_update(db: Session, project_id: int, payload: ProjectUpdate):
    # print_status can only reach "Completed" after the design phase is
    # done - enforced here (not just in the frontend's selectable options)
    # since this is the actual security boundary; the frontend check is a
    # UX nicety that keeps the option from ever being offered.
    if payload.print_status == "Completed":
        project = get_project(db, project_id)
        if not project:
            raise NotFound("Project")
        # Only gate the actual transition into Completed - re-saving a row
        # that's already Completed (editing some other field) shouldn't
        # retroactively break on rows that predate this rule.
        if project.print_status != "Completed" and project.design_completed_at is None:
            raise HTTPException(
                status_code=400,
                detail="Print status can only be marked Completed after the design is marked completed",
            )

    updated = update_project(db, project_id, payload)
    if not updated:
        raise NotFound("Project")
    return updated


def service_mark_design_completed(db: Session, project_id: int, username: str):
    project = get_project(db, project_id)
    if not project:
        raise NotFound("Project")
    return mark_design_completed(db, project_id, username)


def service_mark_print_completed(db: Session, project_id: int, username: str):
    project = get_project(db, project_id)
    if not project:
        raise NotFound("Project")
    # Same rule service_update enforces for this transition via the generic
    # edit path - the real security boundary lives here and there, not in
    # the frontend button's disabled state, which is just a UX nicety.
    if project.print_status != "Completed" and project.design_completed_at is None:
        raise HTTPException(
            status_code=400,
            detail="Print status can only be marked Completed after the design is marked completed",
        )
    return mark_print_completed(db, project_id, username)


def service_mark_delivered(
    db: Session,
    project_id: int,
    username: str,
    on_credit: bool = False,
    is_admin: bool = False,
):
    project = get_project(db, project_id)
    if not project:
        raise NotFound("Project")
    # Enforce the full lifecycle order server-side - the frontend also
    # disables the Delivered button until both conditions are met, but
    # that's a UX nicety, not a security boundary; the real guarantee lives
    # here. Order: design completed -> print status Completed -> delivered.
    if project.design_completed_at is None:
        raise HTTPException(
            status_code=400,
            detail="Design must be marked completed before the order can be marked delivered",
        )
    if project.print_status != "Completed":
        raise HTTPException(
            status_code=400,
            detail="Print status must be Completed before the order can be marked delivered",
        )

    # Payment is only checked on the actual transition - a repeat call on
    # an already-delivered project is a no-op in the repository layer, and
    # delivered_on_credit is a historical fact about how that delivery
    # happened, not something worth re-validating on every idempotent retry.
    if project.delivered_at is None:
        invoice = get_latest_invoice_for_project(db, project_id)
        if not invoice:
            raise HTTPException(
                status_code=400,
                detail="This project must be invoiced before it can be delivered",
            )
        if on_credit:
            # "Deliver on Credit" is a deliberate business decision to ship
            # unpaid work - previously only the frontend restricted this to
            # admins (DeliveryCheck.tsx's canDeliverOnCredit); enforced here
            # too so a direct API call can't let any employee authorize it.
            if not is_admin:
                raise HTTPException(
                    status_code=403,
                    detail="Only an admin can authorize a delivery on credit",
                )
            if invoice.status != "pending":
                raise HTTPException(
                    status_code=400,
                    detail="Delivering on credit only applies to a still-unpaid invoice",
                )
        elif invoice.status != "paid":
            raise HTTPException(
                status_code=400,
                detail="This project's invoice must be paid before it can be delivered - use 'Deliver on Credit' if payment is still pending",
            )

    return mark_delivered(db, project_id, username, on_credit=on_credit)


def service_mark_notified(db: Session, project_id: int, username: str):
    project = get_project(db, project_id)
    if not project:
        raise NotFound("Project")
    return mark_notified(db, project_id, username)


def service_toggle_pin(db: Session, project_id: int):
    project = toggle_pin(db, project_id)
    if not project:
        raise NotFound("Project")
    return project


_INVOICED = "This project has already been invoiced and can't be deleted."


def _bin_entry(project: Project) -> BinEntry:
    label = project.project_type or f"Project #{project.id}"
    if project.customer_name:
        label += f" – {project.customer_name}"
    count = len(project.files)
    return BinEntry("project", project, label, f"{count} {'file' if count == 1 else 'files'}" if count else None)


def service_delete(db: Session, project_id: int, deleted_by: str):
    project = get_project(db, project_id)
    if not project:
        raise NotFound("Project")

    move_to_bin(db, [_bin_entry(project)], deleted_by, _INVOICED)
    return {"message": "Project moved to the bin"}


def service_delete_bulk(db: Session, project_ids: list[int], deleted_by: str):
    projects = (
        db.query(Project)
        .options(selectinload(Project.files))
        .filter(Project.id.in_(project_ids))
        .all()
    )
    # Together: if any of them can't go, none of them do.
    move_to_bin(
        db,
        [_bin_entry(project) for project in projects],
        deleted_by,
        "One or more selected projects have already been invoiced and can't be deleted.",
    )
    return {"message": f"{len(projects)} projects moved to the bin"}
