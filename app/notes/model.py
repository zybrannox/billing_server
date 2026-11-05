from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.datetime_utils import OptionalUTCDateTime, UTCDateTime
from app.response_model import ResponseModel

MAX_NOTE_LENGTH = 5000


def _clean(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    cleaned = text.strip()
    if not cleaned:
        raise ValueError("Write something in the note first.")
    return cleaned


class NoteCreate(BaseModel):
    text: str = Field(max_length=MAX_NOTE_LENGTH)
    customer_id: Optional[int] = None

    _text = field_validator("text")(_clean)


class NoteUpdate(BaseModel):
    text: Optional[str] = Field(default=None, max_length=MAX_NOTE_LENGTH)
    customer_id: Optional[int] = None
    is_done: Optional[bool] = None

    _text = field_validator("text")(_clean)


class NoteRead(ResponseModel):
    id: int
    text: str
    customer_id: Optional[int]
    customer_name: Optional[str]
    created_by: str
    created_at: UTCDateTime
    is_done: bool
    done_at: OptionalUTCDateTime
    done_by: Optional[str]
    invoice_id: Optional[int]
    invoice_number: Optional[str]

    model_config = {"from_attributes": True}


class NoteListResponse(ResponseModel):
    items: List[NoteRead]
    total: int
    # Across all notes, whatever the filter, for the filter's own labels.
    open_count: int
    done_count: int


NoteStatus = Literal["open", "done"]
