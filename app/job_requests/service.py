import math
from datetime import datetime

from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.entities import Customer, Company, Project, ProjectFile, JobRequest, JobRequestFile
from .model import JobRequestCreate, AttachJobRequestFilesRequest, JobRequestRead, JobRequestListResponse


def _to_read(db: Session, job_request: JobRequest) -> JobRequestRead:
    customer = db.get(Customer, job_request.customer_id)
    company = db.get(Company, customer.company_id) if customer and customer.company_id else None
    files = (
        db.query(JobRequestFile)
        .filter(JobRequestFile.job_request_id == job_request.id)
        .order_by(JobRequestFile.id)
        .all()
    )
    return JobRequestRead(
        id=job_request.id,
        customer_id=job_request.customer_id,
        customer_name=f"{customer.first_name} {customer.last_name}" if customer else None,
        company_name=company.name if company else None,
        description=job_request.description,
        status=job_request.status,
        created_at=job_request.created_at,
        project_id=job_request.project_id,
        rejection_reason=job_request.rejection_reason,
        files=files,
    )


class JobRequestService:
    # --- Client side ---

    @staticmethod
    def create(db: Session, client: dict, payload: JobRequestCreate) -> JobRequestRead:
        # Always owned by the specific person who filed it, not the whole
        # company - see entities/job_request.py.
        job_request = JobRequest(customer_id=client["customer_id"], description=payload.description)
        db.add(job_request)
        db.commit()
        db.refresh(job_request)
        return _to_read(db, job_request)

    @staticmethod
    def _get_owned(db: Session, client: dict, job_request_id: int) -> JobRequest:
        job_request = db.get(JobRequest, job_request_id)
        if not job_request:
            raise HTTPException(status_code=404, detail="Job request not found")

        owns = job_request.customer_id == client["customer_id"]
        if not owns and client["company_id"]:
            owner = db.get(Customer, job_request.customer_id)
            owns = bool(owner and owner.company_id == client["company_id"])
        if not owns:
            raise HTTPException(status_code=404, detail="Job request not found")
        return job_request

    @staticmethod
    def attach_files(db: Session, client: dict, job_request_id: int, payload: AttachJobRequestFilesRequest) -> JobRequestRead:
        # Only the filer (not just any contact of their company) can attach
        # files to their own still-open submission.
        job_request = db.get(JobRequest, job_request_id)
        if not job_request or job_request.customer_id != client["customer_id"]:
            raise HTTPException(status_code=404, detail="Job request not found")

        for f in payload.files:
            db.add(
                JobRequestFile(
                    job_request_id=job_request.id,
                    path=f.path,
                    original_name=f.original_name,
                    width=f.width,
                    height=f.height,
                    pixel_width=f.pixel_width,
                    pixel_height=f.pixel_height,
                )
            )
        db.commit()
        return _to_read(db, job_request)

    @staticmethod
    def list_mine(db: Session, client: dict, page: int, page_size: int) -> JobRequestListResponse:
        query = db.query(JobRequest)
        if client["company_id"]:
            contact_ids = [
                c.id for c in db.query(Customer.id).filter(Customer.company_id == client["company_id"]).all()
            ]
            query = query.filter(JobRequest.customer_id.in_(contact_ids))
        else:
            query = query.filter(JobRequest.customer_id == client["customer_id"])

        total = query.count()
        items = query.order_by(JobRequest.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        total_pages = math.ceil(total / page_size) if page_size else 0
        return JobRequestListResponse(
            items=[_to_read(db, jr) for jr in items],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    @staticmethod
    def get_mine(db: Session, client: dict, job_request_id: int) -> JobRequestRead:
        job_request = JobRequestService._get_owned(db, client, job_request_id)
        return _to_read(db, job_request)

    # --- Staff side ---

    @staticmethod
    def list_for_staff(db: Session, page: int, page_size: int, status: str | None = None) -> JobRequestListResponse:
        query = db.query(JobRequest)
        if status:
            query = query.filter(JobRequest.status == status)
        total = query.count()
        items = query.order_by(JobRequest.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        total_pages = math.ceil(total / page_size) if page_size else 0
        return JobRequestListResponse(
            items=[_to_read(db, jr) for jr in items],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    @staticmethod
    def get_for_staff(db: Session, job_request_id: int) -> JobRequestRead:
        job_request = db.get(JobRequest, job_request_id)
        if not job_request:
            raise HTTPException(status_code=404, detail="Job request not found")
        return _to_read(db, job_request)

    @staticmethod
    def convert_to_project(db: Session, job_request_id: int, username: str) -> JobRequestRead:
        job_request = db.get(JobRequest, job_request_id)
        if not job_request:
            raise HTTPException(status_code=404, detail="Job request not found")
        if job_request.status != "pending":
            raise HTTPException(status_code=400, detail=f"This request is already {job_request.status}")

        now = datetime.utcnow()
        # Constructed directly (not via ProjectCreate/create_project), same
        # as create_invoice's own inline "new_project" branch (app/invoices/
        # repository.py) - this project exists to carry work a client
        # already described, not to be scheduled through the ordinary
        # AddProject flow, so it gets the same kind of fixed defaults that
        # branch uses rather than asking staff to re-enter them.
        new_project = Project(
            project_type="Client Job Request",
            description=job_request.description,
            customer_id=job_request.customer_id,
            assigned_to=username,
            priority="Normal",
            client_status="New",
            print_status="In Progress",
            start_date=now,
            delivery_date=now,
        )
        db.add(new_project)
        db.flush()  # assigns new_project.id

        files = db.query(JobRequestFile).filter(JobRequestFile.job_request_id == job_request.id).all()
        for f in files:
            # Re-parented by reference to the same on-disk path - no copy,
            # no re-upload (see app/job_requests/controller.py's upload
            # route, which wrote these bytes via the same save_streaming_
            # file used by the staff-only /files/upload).
            db.add(
                ProjectFile(
                    project_id=new_project.id,
                    path=f.path,
                    original_name=f.original_name,
                    width=f.width,
                    height=f.height,
                    pixel_width=f.pixel_width,
                    pixel_height=f.pixel_height,
                )
            )

        job_request.status = "converted"
        job_request.project_id = new_project.id
        job_request.reviewed_at = now
        job_request.reviewed_by = username

        db.commit()
        db.refresh(job_request)
        return _to_read(db, job_request)

    @staticmethod
    def reject(db: Session, job_request_id: int, username: str, reason: str) -> JobRequestRead:
        job_request = db.get(JobRequest, job_request_id)
        if not job_request:
            raise HTTPException(status_code=404, detail="Job request not found")
        if job_request.status != "pending":
            raise HTTPException(status_code=400, detail=f"This request is already {job_request.status}")

        job_request.status = "rejected"
        job_request.rejection_reason = reason
        job_request.reviewed_at = datetime.utcnow()
        job_request.reviewed_by = username

        db.commit()
        db.refresh(job_request)
        return _to_read(db, job_request)
