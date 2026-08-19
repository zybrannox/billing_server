from pydantic import BaseModel
from typing import Literal, Optional, List
from datetime import datetime
from app.datetime_utils import UTCDateTime, OptionalUTCDateTime

# Low was removed as a priority tier entirely (not just hidden in the UI) -
# reject it at the API boundary rather than relying on the frontend alone.
Priority = Literal["Urgent", "High", "Normal"]


class ProjectBase(BaseModel):
    project_type: str
    assigned_to: str
    priority: Priority
    client_status: str
    print_status: str = "In Progress"
    start_date: UTCDateTime
    delivery_date: UTCDateTime
    description: Optional[str] = None
    customer_id: Optional[int] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    project_type: Optional[str] = None
    assigned_to: Optional[str] = None
    priority: Optional[Priority] = None
    client_status: Optional[str] = None
    print_status: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[datetime] = None
    delivery_date: Optional[datetime] = None
    customer_id: Optional[int] = None
    # design_completed_at/delivered_at are deliberately NOT settable here -
    # they only move through the dedicated, audited /design-completed and
    # /delivered endpoints so the generic edit-in-place table can't be used
    # to fake a milestone (and, later, silently skip the customer notification).


class FileObject(BaseModel):
    path: str
    width: Optional[float] = None
    height: Optional[float] = None
    # Server-side source of truth for "has this file been downloaded" - set
    # by the /files/download endpoints so every user sees the same state,
    # rather than tracking it per-browser on the client.
    downloaded: Optional[bool] = None


class ProjectRead(ProjectBase):
    id: int
    file_paths: List[str | FileObject]
    design_completed_at: OptionalUTCDateTime = None
    design_completed_by: Optional[str] = None
    delivered_at: OptionalUTCDateTime = None
    delivered_by: Optional[str] = None

    model_config = {
        "from_attributes": True
    }


class ProjectBulkDelete(BaseModel):
    ids: List[int]


class ProjectListResponse(BaseModel):
    items: List[ProjectRead]
    total: int
    page: int
    page_size: int
    total_pages: int
