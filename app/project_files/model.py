from pydantic import BaseModel
from typing import Optional, List


class AttachFileEntry(BaseModel):
    path: str
    original_name: Optional[str] = None
    # Stored as physical print size in inches (see utils/appSupport.ts), not pixel counts.
    width: Optional[float] = None
    height: Optional[float] = None


class AttachFilesRequest(BaseModel):
    files: List[AttachFileEntry]


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
