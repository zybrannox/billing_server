import shutil
import uuid
from pathlib import Path
from sqlalchemy.orm import Session
from app.entities import Project, ProjectFile

UPLOAD_DIR = Path("./uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def save_streaming_file(upload_file, filename: str):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # Prefix with a short uuid so concurrent/duplicate filenames never collide
    # (this matters now that files can be uploaded before a project exists).
    ext = Path(filename).suffix
    stored_name = f"{uuid.uuid4().hex}{ext}"
    file_location = UPLOAD_DIR / stored_name

    with file_location.open("wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)

    # Thumbnail generation is deferred to the first /files/thumbnail request
    # (see project_files/controller.py) rather than done here, so uploads
    # aren't slowed down by image processing on the critical path.

    # Only return the stored filename, not path
    return stored_name


def delete_uploaded_file(filename: str) -> bool:
    """Deletes an uploaded file and its thumbnail (if any). Returns True if the file existed."""
    file_path = UPLOAD_DIR / filename
    existed = file_path.exists()
    if existed:
        file_path.unlink()

    thumb_path = UPLOAD_DIR / "thumbnails" / filename
    if thumb_path.exists():
        thumb_path.unlink()

    return existed

def mark_file_downloaded(db: Session, filename: str):
    """Flags a single file as downloaded, server-side, so every user (not
    just the browser that downloaded it) sees it as downloaded.

    Used to scan every project that had any files at all, then walk each
    one's file list in Python looking for a path match - full read of the
    table for one flag flip, and only gets more expensive as projects grow.
    `path` is unique and indexed on project_files (see entities/
    project_file.py), so this is now the single indexed UPDATE it should
    always have been."""
    db.query(ProjectFile).filter(
        ProjectFile.path == filename, ProjectFile.downloaded.is_(False)
    ).update({"downloaded": True})
    db.commit()


def mark_project_files_downloaded(db: Session, project: Project):
    """Flags every file on a project as downloaded (used by the zip/download-all endpoint)."""
    db.query(ProjectFile).filter(
        ProjectFile.project_id == project.id, ProjectFile.downloaded.is_(False)
    ).update({"downloaded": True})
    db.commit()


def delete_project_files(paths: list[str]):
    for filename in paths:
        if not filename:
            continue
        try:
            file_path = UPLOAD_DIR / filename
            if file_path.exists():
                file_path.unlink()  # delete file
        except Exception as e:
            # log but don't fail project deletion
            print(f"Failed to delete file {filename}: {e}")
