from pydantic import BaseModel
from typing import Optional, List

from app.datetime_utils import UTCDateTime
from app.response_model import ResponseModel


class AttachFileEntry(BaseModel):
    path: str
    original_name: Optional[str] = None
    # Stored as physical print size in inches (see utils/appSupport.ts), not pixel counts.
    # This is a 96-DPI *assumption*, not something the file actually declares -
    # treat it as a rough estimate, never an exact billing size.
    width: Optional[float] = None
    height: Optional[float] = None
    # The file's actual, assumption-free pixel dimensions (img.naturalWidth/
    # naturalHeight) - unlike width/height above, this is a plain fact about
    # the file with no DPI guess involved. What GenerateInvoice.tsx shows the
    # user as a reference instead of auto-filling a possibly-wrong size.
    pixel_width: Optional[int] = None
    pixel_height: Optional[int] = None


class AttachFilesRequest(BaseModel):
    files: List[AttachFileEntry]


class FileBulkDeleteRequest(BaseModel):
    paths: List[str]


class InitChunkedUploadRequest(BaseModel):
    filename: str
    total_size: int
    total_chunks: int


class InitChunkedUploadResponse(BaseModel):
    upload_id: str


class CompleteChunkedUploadRequest(BaseModel):
    upload_id: str
    filename: str
    width: Optional[float] = None
    height: Optional[float] = None
    pixel_width: Optional[int] = None
    pixel_height: Optional[int] = None


class ProjectFileRead(ResponseModel):
    """One file of a project, as the gallery needs it."""

    path: str
    original_name: Optional[str]
    is_image: bool
    # True while the full-size original is still on disk. The weekly retention
    # job removes originals of finished projects; the thumbnail stays.
    original_available: bool
    size_bytes: Optional[int]
    pixel_width: Optional[int]
    pixel_height: Optional[int]
    created_at: UTCDateTime
