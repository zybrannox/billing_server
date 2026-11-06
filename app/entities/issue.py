from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.datetime_utils import utcnow


class Issue(Base):
    """A problem an employee reported to the admins from the in-app helper."""

    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Who it belongs to goes by account, not name: a username can be edited and
    # later reused by someone else, who mustn't see these. The name is kept so the
    # issue still reads properly after the account is gone.
    reported_by_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reported_by: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    is_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false(), index=True)
    done_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    done_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # When the reporter saw it was solved. Until then, they still have a notification.
    done_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    @property
    def unseen(self) -> bool:
        return self.is_done and self.done_seen_at is None
