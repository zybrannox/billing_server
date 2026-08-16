from sqlalchemy.orm import Session
from app.entities.project import Project
from .model import ProjectCreate, ProjectUpdate


def create_project(db: Session, project: ProjectCreate):
    new_project = Project(**project.dict())
    db.add(new_project)
    db.commit()
    db.refresh(new_project)
    return new_project


def get_project(db: Session, project_id: int):
    return db.query(Project).filter(Project.id == project_id).first()


def get_all_projects(db: Session, print_status: str | None = None):
    query = db.query(Project)

    if print_status:
        query = query.filter(Project.print_status == print_status)

    return query.all()



def update_project(db: Session, project_id: int, project: ProjectUpdate):
    db_project = get_project(db, project_id)
    if not db_project:  
        return None
    
    for key, value in project.dict(exclude_unset=True).items():
        setattr(db_project, key, value)

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
