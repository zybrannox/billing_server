from typing import List

from app.invoices.calculations import compute_line
from .model import QuotationItemCreate


def compute_quotation_total(items: List[QuotationItemCreate]) -> float:
    return round(sum(compute_line(i.width, i.height, i.rate, i.pieces, i.unit)[1] for i in items), 2)
