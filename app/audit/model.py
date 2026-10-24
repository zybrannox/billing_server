from typing import Any, Optional

from app.datetime_utils import UTCDateTime
from app.response_model import ResponseModel


class AuditLogRead(ResponseModel):
    id: int
    at: UTCDateTime
    actor: str
    action: str
    entity_type: str
    entity_id: Optional[int]
    detail: Optional[dict[str, Any]]


class AuditLogListResponse(ResponseModel):
    items: list[AuditLogRead]
    total: int
    page: int
    page_size: int
    total_pages: int
