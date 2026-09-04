from typing import List, Tuple

from .model import InvoiceItemCreate


def compute_line(width: float, height: float, rate: float) -> Tuple[float, float]:
    """(sq_ft, total) for one line item, rounded to 2 decimals - the single
    source of truth for this math. Used both when actually persisting an
    invoice's items (repository.create_invoice) and when validating a
    payload before that (service_create checks an advance amount against
    the real total) - computing it in two places independently would risk
    them drifting out of sync and rejecting/accepting different amounts
    than what actually gets billed."""
    sq_ft = round(width * height, 2)
    total = round(sq_ft * rate, 2)
    return sq_ft, total


def compute_invoice_total(items: List[InvoiceItemCreate]) -> float:
    return round(sum(compute_line(i.width, i.height, i.rate)[1] for i in items), 2)
