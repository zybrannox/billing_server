from typing import List, Optional

from app.datetime_utils import UTCDateTime
from app.response_model import ResponseModel


class BinItemRead(ResponseModel):
    id: int
    item_type: str
    label: str
    detail: Optional[str]
    size_bytes: int
    deleted_by: str
    deleted_at: UTCDateTime
    expires_at: UTCDateTime

    model_config = {"from_attributes": True}


class BinTypeCount(ResponseModel):
    item_type: str
    count: int


class BinListResponse(ResponseModel):
    items: List[BinItemRead]
    total: int
    # Everything in the bin, whatever the filter, for the filter's own labels.
    counts: List[BinTypeCount]
    total_size_bytes: int
    retention_days: int
