from datetime import datetime

import pytest
from fastapi import HTTPException

from app.entities.project import Project
from app.invoices.model import InvoiceCreate, InvoiceItemCreate, InvoiceUpdate
from app.invoices.repository import create_invoice, get_invoice_payments, update_invoice
from app.invoices.service import service_mark_paid, service_record_payment


@pytest.fixture
def invoice(db):
    project = Project(
        project_type="Flex",
        assigned_to="alan",
        priority="Normal",
        client_status="Confirmed",
        start_date=datetime.utcnow(),
        delivery_date=datetime.utcnow(),
    )
    db.add(project)
    db.commit()
    items = [InvoiceItemCreate(description="Banner", width=10, height=10, rate=10, pieces=1, unit="ft")]
    return create_invoice(db, InvoiceCreate(project_id=project.id, items=items), "tester")  # total 1000


def _sum(db, invoice_id):
    return round(sum(p.amount for p in get_invoice_payments(db, invoice_id)), 2)


def test_invoice_total_is_computed_server_side(invoice):
    assert invoice.amount == 1000 and invoice.balance_due == 1000 and invoice.status == "pending"


def test_partial_payment_reduces_balance_and_keeps_invoice_pending(db, invoice):
    updated = service_record_payment(db, invoice.id, 400, "Cash", "r1", "alan")
    assert updated.balance_due == 600 and updated.status == "pending"
    assert _sum(db, invoice.id) == 400


def test_final_payment_settles_the_invoice(db, invoice):
    service_record_payment(db, invoice.id, 400, "Cash", None, "alan")
    settled = service_record_payment(db, invoice.id, 600, "UPI", "txn", "alan")
    assert settled.status == "paid" and settled.balance_due == 0 and settled.paid_at is not None
    assert _sum(db, invoice.id) == 1000


def test_overpayment_is_rejected(db, invoice):
    with pytest.raises(HTTPException) as err:
        service_record_payment(db, invoice.id, 1000.01, "Cash", None, "alan")
    assert err.value.status_code == 400
    assert _sum(db, invoice.id) == 0


def test_mark_paid_logs_only_the_remaining_balance(db, invoice):
    service_record_payment(db, invoice.id, 250, "Cash", None, "alan")
    service_mark_paid(db, invoice.id, "Card", None, "alan")
    ledger = get_invoice_payments(db, invoice.id)
    assert [p.amount for p in ledger] == [250, 750]
    assert _sum(db, invoice.id) == 1000


def test_cannot_record_against_a_paid_invoice(db, invoice):
    service_mark_paid(db, invoice.id, "Cash", None, "alan")
    with pytest.raises(HTTPException) as err:
        service_record_payment(db, invoice.id, 1, "Cash", None, "alan")
    assert err.value.status_code == 400


def test_lowering_the_advance_is_logged_as_a_negative_adjustment(db, invoice):
    update_invoice(db, invoice.id, InvoiceUpdate(advance_amount=300, payment_method="Cash"), "admin")
    update_invoice(db, invoice.id, InvoiceUpdate(advance_amount=100), "admin")
    assert [p.amount for p in get_invoice_payments(db, invoice.id)] == [300, -200]
    assert _sum(db, invoice.id) == 100  # history always sums to what's been received
