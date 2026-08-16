from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.entities.project import Project
from .repository import (
    create_project,
    get_project,
    get_all_projects,
    update_project,
    delete_project,
    delete_projects
)
from .model import ProjectCreate, ProjectUpdate
from app.project_files.service import delete_project_files


def service_create(db: Session, payload: ProjectCreate):
    return create_project(db, payload)


def service_get(db: Session, project_id: int):
    result = get_project(db, project_id)
    if not result:
        raise HTTPException(status_code=404, detail="Project not found")
    return result


def service_list(db: Session, print_status: str | None = None):
    return get_all_projects(db, print_status)


def service_update(db: Session, project_id: int, payload: ProjectUpdate):
    updated = update_project(db, project_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Project not found")
    return updated


# def service_delete(db: Session, project_id: int):
#     deleted = delete_project(db, project_id)
#     if not deleted:
#         raise HTTPException(status_code=404, detail="Project not found")
#     return {"message": "Project deleted"}



def service_delete(db: Session, project_id: int):
    project = get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Delete files from disk first
    delete_project_files(project.file_paths or [])

    # Delete DB record
    db.delete(project)
    db.commit()

    return {"message": "Project and files deleted successfully"}


def service_delete_bulk(db: Session, project_ids: list[int]):
    # Get projects to find file paths before deletion
    projects = db.query(Project).filter(Project.id.in_(project_ids)).all()

    for project in projects:
        # Delete files from disk
        delete_project_files(project.file_paths or [])

    # Delete DB records using the repository function
    deleted_count = delete_projects(db, project_ids)

    return {"message": f"{deleted_count} projects and their files deleted successfully"}