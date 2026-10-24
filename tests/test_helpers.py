import pytest
from fastapi import HTTPException

from app.errors import BadRequest, NotFound
from app.pagination import page_count
from app.datetime_utils import utcnow


@pytest.mark.parametrize("total,size,pages", [(0, 20, 0), (1, 20, 1), (20, 20, 1), (21, 20, 2), (5, 0, 0)])
def test_page_count(total, size, pages):
    assert page_count(total, size) == pages


def test_errors_are_ordinary_http_exceptions():
    nf, br = NotFound("Customer"), BadRequest("Nope")
    assert isinstance(nf, HTTPException) and (nf.status_code, nf.detail) == (404, "Customer not found")
    assert isinstance(br, HTTPException) and (br.status_code, br.detail) == (400, "Nope")


def test_utcnow_is_naive_utc():
    from datetime import datetime, timezone

    now = utcnow()
    assert now.tzinfo is None
    assert abs((now - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds()) < 5
