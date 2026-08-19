from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.dependencies import get_current_user
from .model import ProjectCreate, ProjectUpdate, ProjectRead, ProjectBulkDelete, ProjectListResponse
from .service import (
    service_create,
    service_list,
    service_get,
    service_update,
    service_delete,
    service_delete_bulk,
    service_mark_design_completed,
    service_mark_delivered,
)

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post("/", response_model=ProjectRead)
def create(payload: ProjectCreate, db: Session = Depends(get_db)):
    return service_create(db, payload)


@router.get("/", response_model=ProjectListResponse)
def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: str | None = None,
    print_status: str | None = None,
    priority: str | None = None,
    customer_id: int | None = None,
    db: Session = Depends(get_db),
):
    return service_list(
        db,
        page=page,
        page_size=page_size,
        search=search,
        print_status=print_status,
        priority=priority,
        customer_id=customer_id,
    )


@router.get("/billing", response_model=ProjectListResponse)
def billing_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return service_list(db, page=page, page_size=page_size, print_status="Completed")



@router.get("/{project_id}", response_model=ProjectRead)
def get_project(project_id: int, db: Session = Depends(get_db)):
    return service_get(db, project_id)


@router.put("/{project_id}", response_model=ProjectRead)
def update_project(project_id: int, payload: ProjectUpdate, db: Session = Depends(get_db)):
    return service_update(db, project_id, payload)


@router.delete("/{project_id}")
def delete_project(project_id: int, db: Session = Depends(get_db)):
    return service_delete(db, project_id)


@router.post("/bulk-delete")
def bulk_delete(payload: ProjectBulkDelete, db: Session = Depends(get_db)):
    return service_delete_bulk(db, payload.ids)


# Auth-gated (any logged-in employee or admin, per get_current_user) and
# server-timestamped - the client never supplies the "when" or "who", only
# the intent to flip the milestone. These are also the two points where a
# future customer-notification call would hook in.
@router.patch("/{project_id}/design-completed", response_model=ProjectRead)
def mark_design_completed(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return service_mark_design_completed(db, project_id, current_user["username"])


@router.patch("/{project_id}/delivered", response_model=ProjectRead)
def mark_delivered(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return service_mark_delivered(db, project_id, current_user["username"])