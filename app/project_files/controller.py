from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse, Response
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth.dependencies import get_current_user
from app.projects.repository import get_project
from app.project_files.service import (
    save_streaming_file,
    delete_uploaded_file,
    mark_file_downloaded,
    mark_project_files_downloaded,
)
from app.project_files.model import AttachFilesRequest
from app.project_files.utils import generate_thumbnail
from app.entities import ProjectFile
from typing import List
from pathlib import Path
from fastapi import Request
from typing import List, Optional
import io
import json
import mimetypes
import os
import zipfile


router = APIRouter(prefix="/files", tags=["Files"])

UPLOAD_DIR = Path("./uploads")


@router.post("/upload/{project_id}")
async def upload_files(
    project_id: int,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    metadata: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # File size limits - Updated for large files
    MAX_FILE_SIZE = 1024 * 1024 * 1024  # 1GB per file
    MAX_TOTAL_SIZE = 2 * 1024 * 1024 * 1024  # 2GB total
    
    # Validate file sizes
    total_size = 0
    for file in files:
        # Read file size by seeking to end
        file.file.seek(0, 2)  # Seek to end
        file_size = file.file.tell()
        file.file.seek(0)  # Reset to beginning
        
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File '{file.filename}' exceeds maximum size of 1GB"
            )
        
        total_size += file_size
    
    if total_size > MAX_TOTAL_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"Total upload size exceeds maximum of 2GB"
        )
    
    parsed_metadata = []
    if metadata:
        try:
            parsed_metadata = json.loads(metadata)
        except json.JSONDecodeError:
            pass

    project = get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    saved_files = []
    for file in files:
        saved_filename = save_streaming_file(file, file.filename)

        # Find matching metadata by filename
        meta = next((m for m in parsed_metadata if m.get("filename") == file.filename), {})

        file_entry = {
            "path": saved_filename,
            "original_name": file.filename,
            "width": meta.get("width"),
            "height": meta.get("height")
        }
        saved_files.append(file_entry)
        db.add(ProjectFile(project_id=project.id, **file_entry))
        # Generating this now (rather than waiting for the first
        # /files/thumbnail request) means the resize/save work is done by
        # the time anyone actually opens the project to look at it, instead
        # of happening synchronously in front of that view. No-ops for
        # non-images (see generate_thumbnail's extension check).
        background_tasks.add_task(generate_thumbnail, saved_filename)

    db.commit()
    return {"message": "uploaded", "file_paths": saved_files}


@router.post("/upload")
async def upload_files_standalone(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    metadata: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
):
    """Uploads files ahead of project creation (Gmail-style: attach now, link later).
    Files are stored immediately but not associated with any project yet -
    call /files/attach/{project_id} afterwards to link them."""

    MAX_FILE_SIZE = 1024 * 1024 * 1024  # 1GB per file
    MAX_TOTAL_SIZE = 2 * 1024 * 1024 * 1024  # 2GB total

    total_size = 0
    for file in files:
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)

        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"File '{file.filename}' exceeds maximum size of 1GB"
            )

        total_size += file_size

    if total_size > MAX_TOTAL_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Total upload size exceeds maximum of 2GB"
        )

    parsed_metadata = []
    if metadata:
        try:
            parsed_metadata = json.loads(metadata)
        except json.JSONDecodeError:
            pass

    saved_files = []
    for file in files:
        saved_filename = save_streaming_file(file, file.filename)
        meta = next((m for m in parsed_metadata if m.get("filename") == file.filename), {})

        saved_files.append({
            "path": saved_filename,
            "original_name": file.filename,
            "width": meta.get("width"),
            "height": meta.get("height"),
        })
        # See upload_files above - pre-generates the thumbnail in the
        # background so it's already there by the time anyone views it,
        # instead of generating on-demand in front of the first viewer.
        background_tasks.add_task(generate_thumbnail, saved_filename)

    return {"files": saved_files}


@router.delete("/{filename}")
def delete_uploaded_file_endpoint(filename: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    # Strip any directory components to prevent path traversal.
    safe_filename = Path(filename).name

    deleted = delete_uploaded_file(safe_filename)
    if not deleted:
        raise HTTPException(status_code=404, detail="File not found")

    # Scrub the file from whichever project had already linked it - path is
    # unique and indexed, so this is one targeted delete instead of loading
    # every project with any files and filtering each one's list in Python.
    db.query(ProjectFile).filter(ProjectFile.path == safe_filename).delete()

    db.commit()
    return {"message": "deleted"}


@router.post("/attach/{project_id}")
def attach_files(project_id: int, payload: AttachFilesRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Links files that were already uploaded via /files/upload to a project,
    without re-uploading their bytes."""

    project = get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    entries = [
        {"path": f.path, "original_name": f.original_name, "width": f.width, "height": f.height}
        for f in payload.files
    ]

    for entry in entries:
        db.add(ProjectFile(project_id=project.id, **entry))
    db.commit()
    return {"message": "attached", "file_paths": entries}


@router.get("/thumbnail/{filename}")
def get_thumbnail(filename: str, current_user: dict = Depends(get_current_user)):
    from .utils import THUMBNAIL_DIR, generate_thumbnail, get_cache_headers
    
    thumb_path = THUMBNAIL_DIR / filename
    if not thumb_path.exists():
        # Try to generate it if it's an image
        res = generate_thumbnail(filename)
        if not res:
            # Fallback to full image or 404
            file_path = UPLOAD_DIR / filename
            if not file_path.exists():
                raise HTTPException(status_code=404, detail="File not found")
            return FileResponse(file_path, headers=get_cache_headers())
    
    return FileResponse(thumb_path, headers=get_cache_headers())


@router.get("/download/{filename}")
def download_file(
    filename: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from .utils import get_cache_headers

    file_path = UPLOAD_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    # mark_file_downloaded scans every project with any files to find which
    # one(s) reference this filename - real work, and it was running before
    # a single byte of the file went out, so every download waited on it
    # even though nothing about the download itself depends on the result.
    # Deferring it to a background task (runs after the response starts,
    # same db session per FastAPI's documented behavior) means the file
    # starts streaming immediately instead.
    background_tasks.add_task(mark_file_downloaded, db, filename)

    return FileResponse(
        file_path,
        media_type="application/octet-stream",
        filename=filename,
        headers=get_cache_headers(),
    )


@router.get("/download/project/{project_id}")
def download_project_files(project_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    project = get_project(db, project_id)

    if not project or not project.file_paths:
        raise HTTPException(status_code=404, detail="No files found for this project")

    mark_project_files_downloaded(db, project)

    from stream_zip import stream_zip, NO_COMPRESSION_64
    import stat
    from datetime import datetime

    def member_files():
        for file_entry in project.file_paths:
            filename = file_entry.path
            file_path = UPLOAD_DIR / filename
            if file_path.exists():
                st = os.stat(file_path)
                modified_at = datetime.fromtimestamp(st.st_mtime)
                mode = stat.S_IFREG | 0o644

                def file_chunks():
                    with open(file_path, "rb") as f:
                        while chunk := f.read(128 * 1024): # 128KB chunks
                            yield chunk

                yield filename, modified_at, mode, NO_COMPRESSION_64, file_chunks()

    return StreamingResponse(
        stream_zip(member_files()),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="project_{project_id}_files.zip"'
        }
    )


@router.get("/view/{filename}")
def view_file(filename: str, request: Request, current_user: dict = Depends(get_current_user)):
    from .utils import get_cache_headers

    file_path = UPLOAD_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    file_size = file_path.stat().st_size
    range_header = request.headers.get("range")
    media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    def iterfile(start=0, end=file_size - 1):
        with open(file_path, "rb") as f:
            f.seek(start)
            while start <= end:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                start += len(chunk)
                yield chunk

    if range_header:
        start, end = range_header.replace("bytes=", "").split("-")
        start = int(start)
        end = int(end) if end else file_size - 1

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(end - start + 1),
            **get_cache_headers(),
        }

        return StreamingResponse(
            iterfile(start, end),
            status_code=206,
            headers=headers,
            media_type=media_type,
        )

    return StreamingResponse(
        iterfile(),
        media_type=media_type,
        headers={"Accept-Ranges": "bytes", **get_cache_headers()},
    )