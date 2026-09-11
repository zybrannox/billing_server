from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.database import get_db
from .model import DashboardSummary, RecentDelivery
from .repository import get_recent_deliveries
from .service import _serialize_recent_deliveries, service_get_summary

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

# Revenue, outstanding balances, top customers - all admin-only financial
# oversight, same boundary as Billing itself.
@router.get("/summary", response_model=DashboardSummary)
def get_summary(
    granularity: Literal["day", "week", "month", "year"] = Query("month"),
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    return service_get_summary(db, granularity=granularity)


# Deliberately its own lightweight endpoint rather than reusing /summary -
# the admin topbar's notification bell polls this on every admin page, not
# just the Dashboard, so it shouldn't have to pull revenue trends, top
# customers, and every other summary field along with it just to show a
# handful of recent deliveries.
@router.get("/notifications/deliveries", response_model=list[RecentDelivery])
def get_delivery_notifications(
    limit: int = Query(8, ge=1, le=20),
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    return _serialize_recent_deliveries(db, get_recent_deliveries(db, limit=limit))
