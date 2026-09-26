import math

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.dependencies import require_admin, get_current_user
from app.companies.model import (
    CompanyCreate,
    CompanyUpdate,
    CompanyRead,
    CompanyListResponse,
    CompanyProfile,
)
from app.companies.service import CompanyService

router = APIRouter(prefix="/companies", tags=["Companies"])


# Admin-only, unlike customers' own POST - a company record carries real
# financial terms (credit limit, payment terms), closer in sensitivity to
# an invoice edit than to ordinary customer intake.
@router.post("/", response_model=CompanyRead)
def create_company(
    company: CompanyCreate,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    return CompanyService.create_company(db, company)


# Open to any authenticated user - the company_id picker on the
# Add/Edit Customer form (see CustomForm's async_select) needs this list
# regardless of role.
@router.get("/", response_model=CompanyListResponse)
def get_companies(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    items, total = CompanyService.get_all_companies(db, page=page, page_size=page_size, search=search)
    total_pages = math.ceil(total / page_size) if page_size else 0
    return CompanyListResponse(
        items=items, total=total, page=page, page_size=page_size, total_pages=total_pages
    )


@router.get("/{company_id}", response_model=CompanyRead)
def get_company(
    company_id: int,
    db: Session = Depends(get_db),
    _user: dict = Depends(get_current_user),
):
    company = CompanyService.get_company_by_id(db, company_id)
    if not company:
        raise HTTPException(404, "Company not found")
    return company


@router.get("/{company_id}/profile", response_model=CompanyProfile)
def get_company_profile(
    company_id: int,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    profile = CompanyService.get_company_profile(db, company_id)
    if not profile:
        raise HTTPException(404, "Company not found")
    return profile


@router.put("/{company_id}", response_model=CompanyRead)
def update_company(
    company_id: int,
    update: CompanyUpdate,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    updated = CompanyService.update_company(db, company_id, update)
    if not updated:
        raise HTTPException(404, "Company not found")
    return updated


@router.delete("/{company_id}")
def delete_company(
    company_id: int,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    deleted = CompanyService.delete_company(db, company_id)
    if not deleted:
        raise HTTPException(404, "Company not found")
    return {"message": "Company deleted successfully"}
