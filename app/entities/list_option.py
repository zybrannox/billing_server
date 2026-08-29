from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, UniqueConstraint

from app.database import Base


class ListOption(Base):
    """One generic table backs every admin-configurable dropdown (Project
    Type today, others later - see conversation) instead of a bespoke table
    per dropdown. `category` is the discriminator ("project_type", etc.);
    everything else about a dropdown's options looks the same regardless of
    which one it is, so there's no reason to duplicate the schema/CRUD per
    category as more of these get added.

    Deactivated (is_active=False), never deleted: a project that already
    used a since-removed option must keep displaying it. Hard-deleting the
    row would orphan that historical data - is_active only hides it from
    the picker for *new* selections going forward.
    """

    __tablename__ = "list_options"
    __table_args__ = (
        # Case sensitivity is handled at the query/insert level (ILIKE /
        # lowercased comparison in the repository) - this constraint is the
        # last-resort guarantee against a race between two concurrent
        # "does it exist yet" checks both deciding to insert.
        UniqueConstraint("category", "value", name="uq_list_option_category_value"),
    )

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(50), nullable=False, index=True)
    value = Column(String(255), nullable=False)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
