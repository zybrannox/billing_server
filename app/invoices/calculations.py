from typing import List, Tuple

from .model import InvoiceItemCreate, MeasurementUnit

# width x height in square inches -> square feet: 12in x 12in = 1 sq ft, so
# divide by 12 x 12. The standard print-industry conversion - see
# compute_line.
SQ_IN_PER_SQ_FT = 144


def compute_line(
    width: float, height: float, rate: float, pieces: int = 1, unit: MeasurementUnit = "ft"
) -> Tuple[float, float]:
    """(sq_ft, total) for one line item, rounded to 2 decimals - the single
    source of truth for this math. Used both when actually persisting an
    invoice's items (repository.create_invoice) and when validating a
    payload before that (service_create checks an advance amount against
    the real total) - computing it in two places independently would risk
    them drifting out of sync and rejecting/accepting different amounts
    than what actually gets billed. `sq_ft` is per-piece (the physical size
    of one item); `total` multiplies in `pieces` since a line can bill for
    more than one identical piece (e.g. 10 identical name boards) without
    needing 10 separate rows.

    `width`/`height` are in whatever `unit` the line was entered in - not
    every job is measured in feet (a name board is more naturally "18in x
    6in" than "1.5ft x 0.5ft"), but the rate is always per square foot
    (matching how this shop actually prices work), so inch-measured lines
    convert to sq_ft here rather than being billed against their raw
    (much larger) inch-squared figure.
    """
    raw_area = width * height
    sq_ft = round(raw_area / SQ_IN_PER_SQ_FT, 2) if unit == "in" else round(raw_area, 2)
    total = round(sq_ft * rate * pieces, 2)
    return sq_ft, total


def compute_invoice_total(items: List[InvoiceItemCreate]) -> float:
    return round(sum(compute_line(i.width, i.height, i.rate, i.pieces, i.unit)[1] for i in items), 2)
