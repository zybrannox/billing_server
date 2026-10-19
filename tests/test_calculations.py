import pytest

from app.invoices.calculations import compute_line


def test_measured_line_in_feet():
    sq_ft, total = compute_line(10, 30, 10, pieces=1, unit="ft")
    assert (sq_ft, total) == (300.0, 3000.0)


def test_pieces_multiply_the_total_not_the_area():
    sq_ft, total = compute_line(8, 4, 10, pieces=4, unit="ft")
    assert sq_ft == 32.0 and total == 1280.0


def test_inches_are_converted_to_square_feet():
    sq_ft, total = compute_line(24, 12, 10, pieces=1, unit="in")  # 288 sq in = 2 sq ft
    assert sq_ft == 2.0 and total == 20.0


def test_others_line_is_rate_times_pieces_with_no_area():
    assert compute_line(0, 0, 250, pieces=3, has_dimensions=False) == (0.0, 750.0)


def test_amounts_are_rounded_to_paise():
    _, total = compute_line(3.33, 3.33, 1, pieces=1)
    assert total == round(total, 2)


@pytest.mark.parametrize("rate", [0, 0.0])
def test_zero_rate_is_allowed(rate):
    assert compute_line(5, 5, rate)[1] == 0.0
