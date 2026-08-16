from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from .model import ProjectCreate, ProjectUpdate, ProjectRead, ProjectBulkDelete
from .service import (
    service_create,
    service_list,
    service_get,
    service_update,
    service_delete,
    service_delete_bulk,
)

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.post("/", response_model=ProjectRead)
def create(payload: ProjectCreate, db: Session = Depends(get_db)):
    return service_create(db, payload)


@router.get("/", response_model=list[ProjectRead])
def list_projects(db: Session = Depends(get_db)):
    return service_list(db)


@router.get("/billing", response_model=list[ProjectRead])
def billing_projects(db: Session = Depends(get_db)):
    return service_list(db, print_status="Completed")



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