from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class ProjectFile(Base):
    """One row per uploaded file, replacing the old projects.file_paths
    JSON blob. That blob had to be scanned in full - every project with
    any files - just to find or update a single file by name (see
    mark_file_downloaded/delete_uploaded_file_endpoint); path is unique and
    indexed here so those become single-row, O(1) lookups instead."""

    __tablename__ = "project_files"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The UUID-based on-disk name (see save_streaming_file) - what every
    # /files/* endpoint addresses the physical file by.
    path = Column(String(255), nullable=False, unique=True, index=True)
    # What the user actually uploaded with - display-only, never used to
    # address the file on disk.
    original_name = Column(String(500), nullable=True)
    width = Column(Float, nullable=True)
    height = Column(Float, nullable=True)
    downloaded = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    project = relationship("Project", back_populates="files")
