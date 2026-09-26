import json
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, UploadFile, File, Form, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.dependencies import get_current_user
from app.client_auth.dependencies import get_current_client
from pathlib import Path
from app.project_files.service import save_streaming_file, delete_uploaded_file
from app.project_files.utils import generate_thumbnail
from .model import (
    JobRequestCreate,
    AttachJobRequestFilesRequest,
    JobRequestRead,
    JobRequestListResponse,
    JobRequestRejectRequest,
)
from .service import JobRequestService

router = APIRouter(prefix="/job-requests", tags=["Job Requests"])

MAX_FILE_SIZE = 1024 * 1024 * 1024  # 1GB per file
MAX_TOTAL_SIZE = 2 * 1024 * 1024 * 1024  # 2GB total


# --- Client side ---

@router.post("/", response_model=JobRequestRead)
def create(payload: JobRequestCreate, db: Session = Depends(get_db), client: dict = Depends(get_current_client)):
    return JobRequestService.create(db, client, payload)


# Client-gated twin of POST /files/upload (upload_files_standalone, see
# app/project_files/controller.py) - deliberately not reusing that staff-
# only route (it's gated by get_current_user, which a client cookie can
# never satisfy - see app/client_auth). Reuses the same disk-level
# functions so files land in the exact same uploads/ store either way; only
# the DB row they're later attached to differs (JobRequestFile, not
# ProjectFile). No chunked-upload path for clients in v1 - see
# GmailFileUploader.tsx's maxFileSize prop, which caps portal uploads at
# CHUNK_UPLOAD_THRESHOLD client-side so this route never has to handle
# anything the chunked-only staff endpoints would otherwise be needed for.
@router.post("/upload")
def upload_files_for_job_request(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    metadata: Optional[str] = Form(None),
    client: dict = Depends(get_current_client),
):
    total_size = 0
    for file in files:
        file.file.seek(0, 2)
        file_size = file.file.tell()
        file.file.seek(0)
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail=f"File '{file.filename}' exceeds maximum size of 1GB")
        total_size += file_size

    if total_size > MAX_TOTAL_SIZE:
        raise HTTPException(status_code=413, detail="Total upload size exceeds maximum of 2GB")

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
        background_tasks.add_task(generate_thumbnail, saved_filename)

    return {"files": saved_files}


# Lets a client remove a file they picked before submitting (mirrors
# AddProject.tsx's cancel-cleanup, which calls the staff-only DELETE
# /files/{filename} for the same reason) - a client session can't call
# that route, so this is a client-gated twin. No JobRequestFile row exists
# yet at this point (see /upload above), so there's nothing to
# ownership-check against beyond the token itself; the on-disk filename is
# an unguessable UUID, the same opaqueness /public/documents/{token} relies
# on.
@router.delete("/upload/{path}")
def delete_own_upload(path: str, client: dict = Depends(get_current_client)):
    safe_name = Path(path).name
    deleted = delete_uploaded_file(safe_name)
    if not deleted:
        raise HTTPException(status_code=404, detail="File not found")
    return {"message": "deleted"}


@router.post("/{job_request_id}/attach-files", response_model=JobRequestRead)
def attach_files(
    job_request_id: int,
    payload: AttachJobRequestFilesRequest,
    db: Session = Depends(get_db),
    client: dict = Depends(get_current_client),
):
    return JobRequestService.attach_files(db, client, job_request_id, payload)


@router.get("/mine", response_model=JobRequestListResponse)
def list_mine(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    client: dict = Depends(get_current_client),
):
    return JobRequestService.list_mine(db, client, page, page_size)


@router.get("/mine/{job_request_id}", response_model=JobRequestRead)
def get_mine(job_request_id: int, db: Session = Depends(get_db), client: dict = Depends(get_current_client)):
    return JobRequestService.get_mine(db, client, job_request_id)


# --- Staff side ---

@router.get("/", response_model=JobRequestListResponse)
def list_for_staff(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    return JobRequestService.list_for_staff(db, page, page_size, status)


@router.get("/{job_request_id}", response_model=JobRequestRead)
def get_for_staff(job_request_id: int, db: Session = Depends(get_db), _user: dict = Depends(get_current_user)):
    return JobRequestService.get_for_staff(db, job_request_id)


@router.post("/{job_request_id}/convert", response_model=JobRequestRead)
def convert(
    job_request_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return JobRequestService.convert_to_project(db, job_request_id, current_user["username"])


@router.post("/{job_request_id}/reject", response_model=JobRequestRead)
def reject(
    job_request_id: int,
    payload: JobRequestRejectRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return JobRequestService.reject(db, job_request_id, current_user["username"], payload.reason)
