from sqlalchemy.orm import Session, selectinload
from fastapi import HTTPException
from app.entities.project import Project
from .repository import (
    create_project,
    get_project,
    get_all_projects,
    update_project,
    delete_project,
    delete_projects,
    mark_design_completed,
    mark_delivered,
)
import math
from .model import ProjectCreate, ProjectUpdate, ProjectListResponse
from app.project_files.service import delete_project_files


def service_create(db: Session, payload: ProjectCreate):
    return create_project(db, payload)


def service_get(db: Session, project_id: int):
    result = get_project(db, project_id)
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return result


def service_list(
    db: Session,
    page: int = 1,
    page_size: int = 10,
    search: str | None = None,
    print_status: str | None = None,
    priority: str | None = None,
    customer_id: int | None = None,
) -> ProjectListResponse:
    items, total = get_all_projects(
        db,
        page=page,
        page_size=page_size,
        search=search,
        print_status=print_status,
        priority=priority,
        customer_id=customer_id,
    )
    total_pages = math.ceil(total / page_size) if page_size else 0
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
            raise HTTPException(status_code=404, detail="Project not found")
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
        raise HTTPException(status_code=404, detail="Project not found")
    return updated


def service_mark_design_completed(db: Session, project_id: int, username: str):
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return mark_design_completed(db, project_id, username)


def service_mark_delivered(db: Session, project_id: int, username: str):
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
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
    return mark_delivered(db, project_id, username)


# def service_delete(db: Session, project_id: int):
#     deleted = delete_project(db, project_id)
#     if not deleted:
#         raise HTTPException(status_code=404, detail="Project not found")
#     return {"message": "Project deleted"}



def service_delete(db: Session, project_id: int):
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Delete files from disk first - the project_files DB rows themselves
    # are handled by the ORM cascade (see Project.files) when the project
    # is deleted below, but that only removes rows, not the bytes on disk.
    delete_project_files([f.path for f in project.files])

    # Delete DB record
    db.delete(project)
    db.commit()

    return {"message": "Project and files deleted successfully"}


def service_delete_bulk(db: Session, project_ids: list[int]):
    # Get projects to find file paths before deletion
    projects = (
        db.query(Project)
        .options(selectinload(Project.files))
        .filter(Project.id.in_(project_ids))
        .all()
    )

    for project in projects:
        # Delete files from disk
        delete_project_files([f.path for f in project.files])

    # Delete DB records using the repository function
    deleted_projects = delete_projects(db, project_ids)

    return {"message": f"{len(deleted_projects)} projects and their files deleted successfully"}