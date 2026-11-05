from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.auth.dependencies import get_current_user, require_admin
from app.auth.permissions import WORKSPACE_MANAGE, require_permission
from .model import ListOptionCreate, ListOptionPricingUpdate, ListOptionRead
from .service import service_list, service_create, service_set_active, service_update_pricing

router = APIRouter(prefix="/list-options", tags=["List Options"])


# Read is open to any authenticated role - everyone filling out a form
# with one of these dropdowns needs to see the current options, not just
# admins. Only adding/removing an option is admin-gated below.
@router.get("/", response_model=List[ListOptionRead])
def list_options(
    category: str,
    active_only: bool = True,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return service_list(db, category, active_only=active_only)


@router.post("/", response_model=ListOptionRead)
def create_option(
    payload: ListOptionCreate,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission(WORKSPACE_MANAGE)),
):
    return service_create(db, payload)


@router.patch("/{option_id}/pricing", response_model=ListOptionRead)
def update_pricing(
    option_id: int,
    payload: ListOptionPricingUpdate,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission(WORKSPACE_MANAGE)),
):
    return service_update_pricing(db, option_id, payload)


@router.patch("/{option_id}/deactivate", response_model=ListOptionRead)
def deactivate_option(
    option_id: int,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission(WORKSPACE_MANAGE)),
):
    return service_set_active(db, option_id, False)


@router.patch("/{option_id}/reactivate", response_model=ListOptionRead)
def reactivate_option(
    option_id: int,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission(WORKSPACE_MANAGE)),
):
    return service_set_active(db, option_id, True)
