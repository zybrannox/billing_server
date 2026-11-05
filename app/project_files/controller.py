from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Form, BackgroundTasks, Query
from app.errors import NotFound, BadRequest
from fastapi.responses import StreamingResponse, FileResponse, Response
from sqlalchemy.orm import Session
from app.database import SessionLocal, get_db
from app.auth.dependencies import get_current_user, require_admin
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
    ProjectFileRead,
)
from app.project_files.utils import generate_thumbnail
from app.project_files import chunked
from app.project_files.retention import purge_stale_originals
from app.bin.service import BinEntry, move_to_bin
from app.entities import Invoice, ProjectFile
from app.project_files.invoice_files import invoiced_files
from typing import List
from pathlib import Path
from fastapi import Request
from typing import List, Optional
import io
import json
import mimetypes
from . import download_progress
from .tracked_response import TrackedFileResponse
from .upload_rules import check_size
import os
import time
import uuid
import zipfile


router = APIRouter(prefix="/files", tags=["Files"])

UPLOAD_DIR = Path("./uploads")

# Downloads sit behind a login, so nothing between here and the browser may
# keep a copy: `public` let Cloudflare cache them by extension (.jpg, .pdf, ...)
# and serve them to anyone holding the URL, and the browser's own cache could
# answer a "download again" with a stale copy.
DOWNLOAD_HEADERS = {"Cache-Control": "private, no-store"}

# A temp zip outlives its download only if the client disconnected before the
# clean-up ran. Long enough that a slow download still in progress is safe.
TEMP_ZIP_MAX_AGE_SECONDS = 6 * 60 * 60

# An id the client makes up to follow a large download by; see download_progress.py.
ProgressId = Query(None, pattern=r"^[0-9a-fA-F-]{16,64}$")


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
        "pixel_width": payload.pixel_width,
        "pixel_height": payload.pixel_height,
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
        check_size(file.filename or "", file_size)
        
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
        raise NotFound("Project")

    saved_files = []
    for file in files:
        saved_filename = save_streaming_file(file, file.filename)

        # Find matching metadata by filename
        meta = next((m for m in parsed_metadata if m.get("filename") == file.filename), {})

        file_entry = {
            "path": saved_filename,
            "original_name": file.filename,
            "width": meta.get("width"),
            "height": meta.get("height"),
            "pixel_width": meta.get("pixel_width"),
            "pixel_height": meta.get("pixel_height"),
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
        check_size(file.filename or "", file_size)

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
            "pixel_width": meta.get("pixel_width"),
            "pixel_height": meta.get("pixel_height"),
        })
        # See upload_files above - pre-generates the thumbnail in the
        # background so it's already there by the time anyone views it,
        # instead of generating on-demand in front of the first viewer.
        background_tasks.add_task(generate_thumbnail, saved_filename)

    return {"files": saved_files}


def _file_bin_entry(record: ProjectFile) -> BinEntry:
    return BinEntry("file", record, record.original_name or record.path, f"From project #{record.project_id}")


@router.delete("/{filename}")
def delete_uploaded_file_endpoint(filename: str, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    # Strip any directory components to prevent path traversal.
    safe_filename = Path(filename).name

    # On a project: goes to the bin. Not on one yet (picked in a form that was
    # then cancelled or changed): nothing was ever saved, so it's just cleaned up.
    record = db.query(ProjectFile).filter(ProjectFile.path == safe_filename).first()
    if record:
        move_to_bin(db, [_file_bin_entry(record)], current_user["username"])
        return {"message": "moved to the bin"}

    if not delete_uploaded_file(safe_filename):
        raise NotFound("File")
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

    records = db.query(ProjectFile).filter(ProjectFile.path.in_(safe_names)).all()
    linked = {r.path for r in records}
    move_to_bin(db, [_file_bin_entry(r) for r in records], current_user["username"])

    cleaned = sum(1 for name in safe_names if name not in linked and delete_uploaded_file(name))
    return {"message": f"{len(linked) + cleaned} files deleted"}


@router.post("/attach/{project_id}")
def attach_files(project_id: int, payload: AttachFilesRequest, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """Links files that were already uploaded via /files/upload to a project,
    without re-uploading their bytes."""

    project = get_project(db, project_id)
    if not project:
        raise NotFound("Project")

    entries = [
        {
            "path": f.path,
            "original_name": f.original_name,
            "width": f.width,
            "height": f.height,
            "pixel_width": f.pixel_width,
            "pixel_height": f.pixel_height,
        }
        for f in payload.files
    ]

    for entry in entries:
        db.add(ProjectFile(project_id=project.id, **entry))
    db.commit()
    return {"message": "attached", "file_paths": entries}


def _gallery_entries(files):
    entries = []
    for f in files:
        path = UPLOAD_DIR / f.path
        exists = path.is_file()
        media_type = mimetypes.guess_type(f.path)[0] or ""
        entries.append(
            {
                "path": f.path,
                "original_name": f.original_name,
                "is_image": media_type.startswith("image/"),
                "original_available": exists and f.original_deleted_at is None,
                "size_bytes": path.stat().st_size if exists else None,
                "pixel_width": f.pixel_width,
                "pixel_height": f.pixel_height,
                "created_at": f.created_at,
            }
        )
    return entries


@router.get("/invoice/{invoice_id}", response_model=List[ProjectFileRead])
def list_invoice_files(invoice_id: int, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    """The files an invoice actually billed for (not everything the project
    holds), with what the gallery needs to choose between the full-size
    original and the thumbnail. See app/project_files/invoice_files.py."""
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise NotFound("Invoice")
    return _gallery_entries(invoiced_files(db, invoice))


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
                raise NotFound("File")
            media_type = mimetypes.guess_type(filename)[0] or ""
            if not media_type.startswith("image/"):
                raise HTTPException(status_code=404, detail="No thumbnail available")
            return FileResponse(file_path, headers=get_cache_headers())

    return FileResponse(thumb_path, headers=get_cache_headers())


@router.get("/download/progress/{progress_id}")
def read_download_progress(progress_id: str, response: Response, current_user: dict = Depends(get_current_user)):
    """How far a large download has got (see download_progress.py)."""
    response.headers["Cache-Control"] = "no-store"
    progress = download_progress.read(progress_id)
    if progress is None:
        raise NotFound("Download")
    return progress


@router.get("/download/{filename}")
def download_file(
    filename: str,
    direct: bool = False,
    progress_id: Optional[str] = ProgressId,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    # Serving the file says nothing about whether it arrived, so by default
    # this doesn't mark it downloaded: the page confirms once it holds the whole
    # file (see the /confirm route below). `direct` is for a large file handed
    # to the browser's download manager, where no page code is left to do that -
    # it's marked when the last byte goes out instead.
    file_path = UPLOAD_DIR / filename
    record = db.query(ProjectFile).filter(ProjectFile.path == filename).first()
    if not file_path.is_file():
        # Distinguish "auto-removed by the weekly retention job" from a
        # plain missing/bad filename - same on-disk symptom, very different
        # explanation, and the frontend shouldn't have to guess which.
        if record and record.original_deleted_at:
            raise HTTPException(
                status_code=410,
                detail="This file's original was automatically removed after "
                "7 days on a completed project. Only the thumbnail remains.",
            )
        raise NotFound("File")

    save_as = (record.original_name if record else None) or filename
    # Don't hold one of the few pooled connections for the whole transfer.
    db.close()

    if direct:
        return TrackedFileResponse(
            file_path,
            media_type="application/octet-stream",
            filename=save_as,
            headers=DOWNLOAD_HEADERS,
            on_complete=lambda: _record_file_downloaded(filename),
            progress_id=progress_id,
        )
    return FileResponse(
        file_path,
        media_type="application/octet-stream",
        filename=save_as,
        headers=DOWNLOAD_HEADERS,
    )


# These run after the response, long after the request's own session has closed.
def _record_file_downloaded(filename: str) -> None:
    with SessionLocal() as db:
        mark_file_downloaded(db, filename)


def _record_project_downloaded(project_id: int) -> None:
    with SessionLocal() as db:
        project = get_project(db, project_id)
        if project:
            mark_project_files_downloaded(db, project)


@router.post("/download/{filename}/confirm")
def confirm_file_downloaded(
    filename: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Called by the client once it holds the complete file and has handed it
    to the browser to save - the only point a download is known to have worked."""
    if not db.query(ProjectFile).filter(ProjectFile.path == filename).first():
        raise NotFound("File")
    mark_file_downloaded(db, filename)
    return {"downloaded": True}


@router.get("/download/project/{project_id}")
def download_project_files(
    project_id: int,
    background_tasks: BackgroundTasks,
    direct: bool = False,
    progress_id: Optional[str] = ProgressId,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    project = get_project(db, project_id)

    if not project or not project.file_paths:
        raise HTTPException(status_code=404, detail="No files found for this project")

    available = [
        (UPLOAD_DIR / f.path, f.original_name or f.path)
        for f in project.file_paths
        if (UPLOAD_DIR / f.path).is_file()
    ]
    if not available:
        raise HTTPException(
            status_code=410,
            detail="None of this project's original files are available any more.",
        )
    # Nothing below needs the database: don't hold one of the few pooled
    # connections for as long as the zip takes to build and send.
    db.close()

    if direct and progress_id:
        download_progress.begin(progress_id)

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

    cutoff = time.time() - TEMP_ZIP_MAX_AGE_SECONDS
    for old_zip in temp_zip_dir.glob("*.zip"):
        if old_zip.stat().st_mtime < cutoff:
            old_zip.unlink(missing_ok=True)

    try:
        with zipfile.ZipFile(temp_zip_path, "w", zipfile.ZIP_STORED) as zf:
            for file_path, arcname in available:
                # The in-zip name a person actually sees on extract -
                # the on-disk name is only the UUID-based storage name.
                zf.write(file_path, arcname=arcname)
    except OSError:
        temp_zip_path.unlink(missing_ok=True)
        if direct and progress_id:
            download_progress.stopped(progress_id)
        raise

    background_tasks.add_task(lambda: temp_zip_path.unlink(missing_ok=True))

    # See download_file for what `direct` means.
    if direct:
        return TrackedFileResponse(
            temp_zip_path,
            media_type="application/zip",
            filename=f"project_{project_id}_files.zip",
            headers=DOWNLOAD_HEADERS,
            on_complete=lambda: _record_project_downloaded(project_id),
            progress_id=progress_id,
        )
    return FileResponse(
        temp_zip_path,
        media_type="application/zip",
        filename=f"project_{project_id}_files.zip",
        headers=DOWNLOAD_HEADERS,
    )


@router.post("/download/project/{project_id}/confirm")
def confirm_project_downloaded(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Same as confirm_file_downloaded, for a "download all" zip."""
    project = get_project(db, project_id)
    if not project:
        raise NotFound("Project")
    mark_project_files_downloaded(db, project)
    return {"downloaded": True}


@router.get("/view/{filename}")
def view_file(
    filename: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    from .utils import get_cache_headers

    file_path = UPLOAD_DIR / filename
    if not file_path.exists():
        record = db.query(ProjectFile).filter(ProjectFile.path == filename).first()
        if record and record.original_deleted_at:
            raise HTTPException(
                status_code=410,
                detail="This file's original was automatically removed after "
                "7 days on a completed project. Only the thumbnail remains.",
            )
        raise NotFound("File")

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
        raise BadRequest("Not an image file")

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


@router.post("/purge-stale")
def purge_stale_files(db: Session = Depends(get_db), _admin: dict = Depends(require_admin)):
    """Manually runs the weekly storage-retention job on demand (see
    app/project_files/retention.py and the scheduled call in app/main.py).
    Admin-only, since it permanently deletes original files - useful for
    ops (run it right now instead of waiting for Sunday) and for verifying
    the job actually does what it says without waiting a week."""
    return purge_stale_originals(db)