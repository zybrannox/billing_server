from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.datetime_utils import OptionalUTCDateTime, UTCDateTime
from app.response_model import ResponseModel

IssueStatus = Literal["open", "done"]
MAX_ISSUE_LENGTH = 2000


class IssueCreate(BaseModel):
    text: str = Field(max_length=MAX_ISSUE_LENGTH)

    @field_validator("text")
    @classmethod
    def says_something(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Tell us what's wrong first.")
        return cleaned


class IssueUpdate(BaseModel):
    is_done: bool


class IssueRead(ResponseModel):
    id: int
    text: str
    reported_by: str
    created_at: UTCDateTime
    is_done: bool
    done_at: OptionalUTCDateTime
    done_by: Optional[str]

    model_config = {"from_attributes": True}


class IssueListResponse(ResponseModel):
    items: List[IssueRead]
    total: int
    open_count: int
    done_count: int


class MyIssue(IssueRead):
    # Solved, and the reporter hasn't seen that yet.
    unseen: bool


class MyIssuesResponse(ResponseModel):
    items: List[MyIssue]
    unseen_count: int
