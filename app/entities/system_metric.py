from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.datetime_utils import utcnow


class SystemMetric(Base):
    """One health snapshot a minute (7 days kept) so a lag spike that happened
    an hour ago - or overnight - can still be seen and explained."""

    __tablename__ = "system_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    memory_available_pct: Mapped[float] = mapped_column(Float, nullable=False)
    swap_used_mb: Mapped[float] = mapped_column(Float, nullable=False)
    load_per_core: Mapped[float] = mapped_column(Float, nullable=False)
    disk_free_pct: Mapped[float] = mapped_column(Float, nullable=False)
    app_memory_mb: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    db_connections_in_use: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    p95_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
