from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from app.database import Base


class JobRequestFile(Base):
    """One row per file a client attached to a JobRequest (see
    app/job_requests). Mirrors ProjectFile's columns exactly, but stays a
    dedicated table rather than a nullable project_id on ProjectFile itself
    - ProjectFile.project_id is NOT NULL and this keeps it that way, with
    no blast radius on that existing table. Once a request is converted to
    a real Project (see JobRequestService.convert_to_project), a matching
    ProjectFile row is created pointing at the same on-disk `path` - no
    file copy, no re-upload.
    """

    __tablename__ = "job_request_files"

    id = Column(Integer, primary_key=True, index=True)
    job_request_id = Column(
        Integer, ForeignKey("job_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    path = Column(String(255), nullable=False, unique=True, index=True)
    original_name = Column(String(500), nullable=True)
    width = Column(Float, nullable=True)
    height = Column(Float, nullable=True)
    pixel_width = Column(Integer, nullable=True)
    pixel_height = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
