"""The handful of HTTP errors the API raises over and over.

They are plain HTTPException subclasses, so FastAPI renders them exactly as
before ({"detail": "..."}); the point is one place for the wording and status
codes instead of 100+ hand-written `HTTPException(404, "... not found")`.
"""
from fastapi import HTTPException


class NotFound(HTTPException):
    def __init__(self, entity: str):
        super().__init__(status_code=404, detail=f"{entity} not found")


class BadRequest(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status_code=400, detail=detail)
