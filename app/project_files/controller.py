from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form
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
from app.entities import Project
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

    saved_files = []
    for file in files:
        saved_filename = save_streaming_file(file, file.filename)
        
        # Find matching metadata by filename
        meta = next((m for m in parsed_metadata if m.get("filename") == file.filename), {})
        
        file_entry = {
            "path": saved_filename,
            "width": meta.get("width"),
            "height": meta.get("height")
        }
        saved_files.append(file_entry)

    project = get_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
        
    project.file_paths = (project.file_paths or []) + saved_files
    db.commit()
    db.refresh(project)
    return {"message": "uploaded", "file_paths": saved_files}


@router.post("/upload")
async def upload_files_standalone(
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

    return {"files": saved_files}


@router.delete("/{filename}")
def delete_uploaded_file_endpoint(filename: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    # Strip any directory components to prevent path traversal.
    safe_filename = Path(filename).name

    deleted = delete_uploaded_file(safe_filename)
    if not deleted:
        raise HTTPException(status_code=404, detail="File not found")

    # Scrub the file from any project that had already linked it.
    projects = db.query(Project).filter(Project.file_paths.isnot(None)).all()
    for project in projects:
        paths = project.file_paths or []
        new_paths = [
            p for p in paths
            if (p.get("path") if isinstance(p, dict) else p) != safe_filename
        ]
        if len(new_paths) != len(paths):
            project.file_paths = new_paths

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
        {"path": f.path, "width": f.width, "height": f.height}
        for f in payload.files
    ]

    project.file_paths = (project.file_paths or []) + entries
    db.commit()
    db.refresh(project)
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
def download_file(filename: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    from .utils import get_cache_headers

    file_path = UPLOAD_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    mark_file_downloaded(db, filename)

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
            filename = file_entry.get("path") if isinstance(file_entry, dict) else file_entry
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