from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class ProjectBase(BaseModel):
    project_type: str
    assigned_to: str
    priority: str
    client_status: str
    print_status: str = "Pending"
    start_date: datetime
    delivery_date: datetime
    description: Optional[str] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    project_type: Optional[str]
    assigned_to: Optional[str]
    priority: Optional[str]
    client_status: Optional[str]
    print_status: Optional[str]
    description: Optional[str]
    start_date: Optional[datetime] = None
    delivery_date: Optional[datetime] = None


class FileObject(BaseModel):
    path: str
    width: Optional[float] = None
    height: Optional[float] = None


class ProjectRead(ProjectBase):
    id: int
    file_paths: List[str | FileObject]

    class Config:
        orm_mode = True


class ProjectBulkDelete(BaseModel):
    ids: List[int]
