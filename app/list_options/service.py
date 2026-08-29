from sqlalchemy.orm import Session
from fastapi import HTTPException

from .repository import get_options, create_option, set_active
from .model import ListOptionCreate


def service_list(db: Session, category: str, active_only: bool = True):
    return get_options(db, category, active_only=active_only)


def service_create(db: Session, payload: ListOptionCreate):
    option, created = create_option(db, payload.category, payload.value)
    if not created:
        raise HTTPException(
            status_code=400,
            detail=f'"{payload.value}" already exists in {payload.category}',
        )
    return option


def service_set_active(db: Session, option_id: int, is_active: bool):
    option = set_active(db, option_id, is_active)
    if not option:
        raise HTTPException(status_code=404, detail="Option not found")
    return option
