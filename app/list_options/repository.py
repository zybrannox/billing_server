from sqlalchemy import func
from sqlalchemy.orm import Session

from app.entities.list_option import ListOption


def get_options(db: Session, category: str, active_only: bool = True):
    query = db.query(ListOption).filter(ListOption.category == category)
    if active_only:
        query = query.filter(ListOption.is_active.is_(True))
    return query.order_by(ListOption.sort_order, ListOption.id).all()


def find_by_value(db: Session, category: str, value: str):
    # Case-insensitive - "Flex" and "flex" are the same option to a user
    # picking from a dropdown, even though the unique constraint alone
    # (case-sensitive) wouldn't catch that collision.
    return (
        db.query(ListOption)
        .filter(
            ListOption.category == category,
            func.lower(ListOption.value) == value.lower(),
        )
        .first()
    )


def create_option(
    db: Session, category: str, value: str, rate: float | None = None
) -> tuple[ListOption, bool]:
    """Returns (option, created). If a matching option already exists and
    is active, that's a duplicate - the caller decides how to respond. If
    it exists but was deactivated, reactivates and reuses that row instead
    of inserting a second one for the same value - and refreshes its rate
    to whatever was just submitted, in case pricing changed since it was
    removed."""
    existing = find_by_value(db, category, value)
    if existing:
        if existing.is_active:
            return existing, False
        existing.is_active = True
        existing.rate = rate
        db.commit()
        db.refresh(existing)
        return existing, True

    max_sort = (
        db.query(func.max(ListOption.sort_order))
        .filter(ListOption.category == category)
        .scalar()
        or 0
    )
    option = ListOption(
        category=category,
        value=value,
        rate=rate,
        sort_order=max_sort + 1,
        is_active=True,
    )
    db.add(option)
    db.commit()
    db.refresh(option)
    return option, True


def get_option(db: Session, option_id: int):
    return db.query(ListOption).filter(ListOption.id == option_id).first()


def set_active(db: Session, option_id: int, is_active: bool):
    option = get_option(db, option_id)
    if not option:
        return None
    option.is_active = is_active
    db.commit()
    db.refresh(option)
    return option
