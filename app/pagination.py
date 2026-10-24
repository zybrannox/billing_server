"""Shared paging maths, so every list endpoint pages the same way."""
import math

from sqlalchemy.orm import Query


def page_count(total: int, page_size: int) -> int:
    """Number of pages needed for `total` rows (0 when page_size is 0)."""
    return math.ceil(total / page_size) if page_size else 0


def paginate(query: Query, page: int, page_size: int) -> Query:
    """Limit a query to the 1-based `page`."""
    return query.offset((page - 1) * page_size).limit(page_size)
