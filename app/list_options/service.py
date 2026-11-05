from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.errors import NotFound

from .repository import get_options, create_option, set_active
from .model import ListOptionCreate, ListOptionPricingUpdate, PRICED_CATEGORIES
from app.entities.list_option import ListOption


def service_list(db: Session, category: str, active_only: bool = True):
    return get_options(db, category, active_only=active_only)


def service_create(db: Session, payload: ListOptionCreate):
    option, created = create_option(db, payload.category, payload.value, payload.rate)
    if not created:
        raise HTTPException(
            status_code=400,
            detail=f'"{payload.value}" already exists in {payload.category}',
        )
    return option


def service_set_active(db: Session, option_id: int, is_active: bool):
    option = set_active(db, option_id, is_active)
    if not option:
        raise NotFound("Option")
    return option


def service_update_pricing(db: Session, option_id: int, payload: ListOptionPricingUpdate):
    option = db.get(ListOption, option_id)
    if not option:
        raise NotFound("Option")
    if option.category not in PRICED_CATEGORIES:
        raise HTTPException(status_code=400, detail="This kind of option has no price.")
    option.rate = payload.rate
    option.min_charges = [tier.model_dump() for tier in payload.min_charges] or None
    db.commit()
    db.refresh(option)
    return option
