from pydantic import BaseModel
from typing import List, Optional
from app.datetime_utils import UTCDateTime, OptionalUTCDateTime


class JobRequestCreate(BaseModel):
    description: str


# Same shape as AttachFileEntry (app/project_files/model.py) - the response
# of POST /job-requests/upload, echoed back to identify which already-
# uploaded files to attach.
class JobRequestFileEntry(BaseModel):
    path: str
    original_name: Optional[str] = None
    width: Optional[float] = None
    height: Optional[float] = None
    pixel_width: Optional[int] = None
    pixel_height: Optional[int] = None


class AttachJobRequestFilesRequest(BaseModel):
    files: List[JobRequestFileEntry]


class JobRequestFileRead(BaseModel):
    id: int
    path: str
    original_name: Optional[str] = None
    width: Optional[float] = None
    height: Optional[float] = None
    pixel_width: Optional[int] = None
    pixel_height: Optional[int] = None

    model_config = {"from_attributes": True}


class JobRequestRead(BaseModel):
    id: int
    customer_id: int
    customer_name: Optional[str] = None
    company_name: Optional[str] = None
    description: str
    status: str
    created_at: UTCDateTime
    project_id: Optional[int] = None
    rejection_reason: Optional[str] = None
    files: List[JobRequestFileRead] = []

    model_config = {"from_attributes": True}


class JobRequestListResponse(BaseModel):
    items: List[JobRequestRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class JobRequestRejectRequest(BaseModel):
    reason: str
