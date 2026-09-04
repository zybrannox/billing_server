from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.dependencies import require_admin
from app.database import get_db
from .model import DashboardSummary
from .service import service_get_summary

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
