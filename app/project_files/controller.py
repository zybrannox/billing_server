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
from app.project_files.model import (
    AttachFilesRequest,
    FileBulkDeleteRequest,
    InitChunkedUploadRequest,
    InitChunkedUploadResponse,
    CompleteChunkedUploadRequest,
)
from app.project_files.utils import generate_thumbnail
from app.project_files import chunked
from app.entities import ProjectFile
from typing import List
from pathlib import Path
from fastapi import Request
from typing import List, Optional
import io
import json
import mimetypes
import os
import uuid
import zipfile


router = APIRouter(prefix="/files", tags=["Files"])

UPLOAD_DIR = Path("./uploads")


# These three must be registered before /upload/{project_id} below - as a
# path *parameter* route, "/upload/init" would otherwise match that pattern
# first (with "init" as an invalid project_id) and never reach these at all.
# FastAPI/Starlette matches routes in registration order, not by specificity.
@router.post("/upload/init", response_model=InitChunkedUploadResponse)
def init_chunked_upload(
    payload: InitChunkedUploadRequest,
    current_user: dict = Depends(get_current_user),
):
    upload_id = chunked.init_upload(
        payload.filename, payload.total_size, payload.total_chunks
    )
    return InitChunkedUploadResponse(upload_id=upload_id)


@router.post("/upload/chunk")
def upload_chunk(
    upload_id: str = Form(...),
    chunk_index: int = Form(...),
    chunk: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    # `def`, not `async def` - see upload_files below for why (blocking
    # disk I/O with no `await` must not run on the event loop thread).
    data = chunk.file.read()
    chunked.write_chunk(upload_id, chunk_index, data)
    return {"received": True}


@router.post("/upload/complete")
def complete_chunked_upload(
    payload: CompleteChunkedUploadRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    stored_name = chunked.complete_upload(payload.upload_id)
    # See upload_files below - pre-generates the thumbnail in the
    # background rather than on the first /files/thumbnail request.
    background_tasks.add_task(generate_thumbnail, stored_name)
    return {
        "path": stored_name,
        "original_name": payload.filename,
        "width": payload.width,
        "height": payload.height,
    }


@router.post("/upload/{project_id}")
def upload_files(
    project_id: int,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    metadata: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # `def`, not `async def`: save_streaming_file below is a blocking disk
    # write with no `await`. Inside an async route that would freeze the
    # single event loop thread for the whole duration of the copy - not just
    # slow for this upload, but unresponsive for every other request the
    # server is handling, for as long as a large file takes to write. A
    # plain `def` route runs in FastAPI's worker thread pool instead, so a
    # slow upload only occupies one thread while everything else keeps going.
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
def upload_files_standalone(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    metadata: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user),
):
    # See upload_files above for why this is `def`, not `async def`.
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


@router.post("/bulk-delete")
def bulk_delete_files(
    payload: FileBulkDeleteRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Same operation as DELETE /{filename}, batched - one DB round trip
    for however many files were selected instead of one request per file.
    Resilient to a file already being gone (skips it, doesn't fail the
    whole batch) since a multi-select delete shouldn't 404 on the first
    already-removed entry and abandon the rest."""
    safe_names = [Path(p).name for p in payload.paths if p]
    if not safe_names:
        return {"message": "0 files deleted"}

    deleted_count = sum(1 for name in safe_names if delete_uploaded_file(name))

    db.query(ProjectFile).filter(ProjectFile.path.in_(safe_names)).delete(
        synchronize_session=False
    )
    db.commit()

    return {"message": f"{deleted_count} files deleted"}


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
            # No thumbnail exists and none could be generated - fall back to
            # the original file only if it's actually an image Pillow just
            # doesn't handle (thumbnail generation failing doesn't mean
            # "not an image"). Anything else (docs, archives, and now -
            # since uploads accept whatever Gmail would - things like .html)
            # must never be served here with no Content-Disposition and a
            # Content-Type guessed from the extension: unlike /files/view,
            # this had no image/* check at all, so this was a real stored-
            # XSS path the moment a non-image type became uploadable.
            file_path = UPLOAD_DIR / filename
            if not file_path.exists():
                raise HTTPException(status_code=404, detail="File not found")
            media_type = mimetypes.guess_type(filename)[0] or ""
            if not media_type.startswith("image/"):
                raise HTTPException(status_code=404, detail="No thumbnail available")
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
def download_project_files(
    project_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    project = get_project(db, project_id)

    if not project or not project.file_paths:
        raise HTTPException(status_code=404, detail="No files found for this project")

    mark_project_files_downloaded(db, project)

    # Built to a temp file first rather than streamed straight to the
    # client - a streaming response's eventual size isn't known upfront, so
    # it can't set Content-Length, which meant the download progress
    # indicator had no actual total to show, only bytes-received-so-far.
    # Serving a real file here gives it one for free, the same way single-
    # file downloads already report "X of Y" - no frontend changes needed.
    # Files are stored uncompressed (ZIP_STORED, matching the previous
    # NO_COMPRESSION_64 streaming version) - this is a fast concatenation,
    # not real compression work, so building before serving doesn't
    # meaningfully delay the download starting.
    temp_zip_dir = UPLOAD_DIR / ".tmp_zips"
    temp_zip_dir.mkdir(parents=True, exist_ok=True)
    temp_zip_path = temp_zip_dir / f"{uuid.uuid4().hex}.zip"

    with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_STORED) as zf:
        for file_entry in project.file_paths:
            file_path = UPLOAD_DIR / file_entry.path
            if file_path.exists():
                # The in-zip name a person actually sees on extract -
                # `.path` is only the UUID-based storage name.
                zf.write(file_path, arcname=file_entry.original_name or file_entry.path)

    background_tasks.add_task(lambda: temp_zip_path.unlink(missing_ok=True))

    return FileResponse(
        temp_zip_path,
        media_type="application/zip",
        filename=f"project_{project_id}_files.zip",
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

    # This endpoint exists for inline image preview (see FilePreview.tsx,
    # which only ever calls it for image files) - never serve anything else
    # here with a browser-renderable Content-Type. Non-image files already
    # can't reach upload storage at all (see save_streaming_file's
    # extension allowlist), but this is the second, independent check: even
    # a file that predates that allowlist, or reached disk some other way,
    # still can't be served back as executable/renderable content.
    if not media_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Not an image file")

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