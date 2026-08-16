from pydantic import BaseModel
from typing import Optional, List


class AttachFileEntry(BaseModel):
    path: str
    # Stored as physical print size in inches (see utils/appSupport.ts), not pixel counts.
    width: Optional[float] = None
    height: Optional[float] = None


class AttachFilesRequest(BaseModel):
    files: List[AttachFileEntry]
