"""One payment from a customer, split across their invoices, with the rest kept as credit."""
from datetime import datetime, timedelta

import pytest
from passlib.hash import bcrypt

from app.datetime_utils import utcnow
from app.entities import BinItem, Customer, CustomerPayment, Invoice, InvoicePayment, User, UserRole
from app.entities.project import Project
from app.security import create_access_token


def _sign_in(client, db, name, role):
    db.add(User(username=name, email=f"{name}@example.com", phone=str(9000000000 + abs(hash(name)) % 999999999)[:10],
                hashed_password=bcrypt.hash("x" * 12), role=role, is_active=True, permissions=[]))
    db.commit()
    client.cookies.set("access_token", create_access_token({"sub": name, "role": role.value, "tv": 0}))
    client.headers["X-Requested-With"] = "XMLHttpRequest"


@pytest.fixture
def admin(client, db):
    _sign_in(client, db, "boss", UserRole.ADMIN)


def _customer(db, first="Meera", phone="9876543210"):
    row = Customer(first_name=first, last_name="S", contact_number=phone)
    db.add(row)
    db.commit()
    return row


@pytest.fixture
def customer(db):
    return _customer(db)


def _invoice(db, customer, amount, on, advance=0, status="pending"):
    project = Project(project_type="Flex", assigned_to="boss", priority="Normal", client_status="Confirmed",
                      print_status="Completed", start_date=on, delivery_date=on, customer_id=customer.id)
    db.add(project)
    db.flush()
    invoice = Invoice(project_id=project.id, status=status, subtotal=amount, discount_amount=0, amount=amount,
                      advance_amount=advance, created_at=on)
    db.add(invoice)
    db.flush()
    invoice.invoice_number = f"INV-2026-{invoice.id:05d}"
    if advance:
        db.add(InvoicePayment(invoice_id=invoice.id, amount=advance, payment_method="Cash", recorded_by="boss"))
    db.commit()
    return invoice.id


@pytest.fixture
def three(db, customer):
    """₹3,000 (Sep), ₹4,000 (Oct, ₹500 already paid), ₹2,500 (Nov)."""
    return [
        _invoice(db, customer, 3000, datetime(2026, 9, 1)),
        _invoice(db, customer, 4000, datetime(2026, 10, 1), advance=500),
        _invoice(db, customer, 2500, datetime(2026, 11, 1)),
    ]


def _state(db, invoice_id):
    db.expire_all()
    i = db.get(Invoice, invoice_id)
    return i.status, i.advance_amount, i.balance_due


def _ledger_matches(db, *invoice_ids):
    db.expire_all()
    for invoice_id in invoice_ids:
        invoice = db.get(Invoice, invoice_id)
        total = round(sum(p.amount for p in db.query(InvoicePayment).filter_by(invoice_id=invoice_id)), 2)
        assert total == invoice.advance_amount, f"history of {invoice.invoice_number} doesn't add up"


def _pay(client, customer, amount, allocations, **extra):
    return client.post(f"/customers/{customer.id}/payments", json={
        "amount": amount, "payment_method": "UPI", "payment_reference": "txn-1",
        "allocations": [{"invoice_id": i, "amount": a} for i, a in allocations], **extra,
    })


def test_open_invoices_are_this_customers_unpaid_ones_oldest_first(client, db, admin, customer, three):
    other = _customer(db, "Ravi", "9876500000")
    _invoice(db, other, 999, datetime(2026, 8, 1))
    _invoice(db, customer, 700, datetime(2026, 8, 15), status="paid", advance=700)
    body = client.get(f"/customers/{customer.id}/open-invoices").json()
    assert [(r["id"], r["balance_due"]) for r in body] == [(three[0], 3000), (three[1], 3500), (three[2], 2500)]


def test_one_payment_settles_several_invoices(client, db, admin, customer, three):
    res = _pay(client, customer, 8000, [(three[0], 3000), (three[1], 3500), (three[2], 1500)])
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["unused"] == 0
    assert [(a["invoice_id"], a["amount"]) for a in body["applied_to"]] == [(three[0], 3000), (three[1], 3500), (three[2], 1500)]
    assert _state(db, three[0]) == ("paid", 3000, 0)
    assert _state(db, three[1]) == ("paid", 4000, 0)
    assert _state(db, three[2]) == ("pending", 1500, 1000)
    _ledger_matches(db, *three)
    # Each invoice's own history says where the money came from.
    history = client.get(f"/invoices/{three[2]}/payments").json()
    assert history[-1]["customer_payment_id"] == body["id"] and history[-1]["amount"] == 1500


def test_what_isnt_split_stays_as_credit_and_can_be_used_later(client, db, admin, customer, three):
    body = _pay(client, customer, 5000, [(three[0], 3000)]).json()
    assert body["unused"] == 2000
    assert client.get(f"/customers/{customer.id}/profile").json()["stats"]["credit"] == 2000
    assert client.get(f"/customers/{customer.id}/payments").json()["credit"] == 2000

    res = client.post(f"/customer-payments/{body['id']}/apply", json={"allocations": [{"invoice_id": three[2], "amount": 2000}]})
    assert res.status_code == 200, res.text
    assert res.json()["unused"] == 0
    assert _state(db, three[2]) == ("pending", 2000, 500)
    # Can't spend the same credit twice.
    again = client.post(f"/customer-payments/{body['id']}/apply", json={"allocations": [{"invoice_id": three[1], "amount": 1}]})
    assert again.status_code == 400
    _ledger_matches(db, *three)


@pytest.mark.parametrize("allocations, why", [
    ([(0, 3000), (1, 3500), (2, 2500)], "more than the payment"),
    ([(0, 3000.01)], "more than the invoice's balance"),
])
def test_a_bad_split_saves_nothing(client, db, admin, customer, three, allocations, why):
    res = _pay(client, customer, 8000, [(three[i], a) for i, a in allocations])
    assert res.status_code == 400, why
    assert db.query(CustomerPayment).count() == 0
    assert _state(db, three[0]) == ("pending", 0, 3000)
    _ledger_matches(db, *three)


def test_only_this_customers_pending_invoices_can_be_paid(client, db, admin, customer, three):
    other = _customer(db, "Ravi", "9876500000")
    theirs = _invoice(db, other, 1000, datetime(2026, 10, 1))
    paid = _invoice(db, customer, 1000, datetime(2026, 10, 1), status="paid", advance=1000)
    cancelled = _invoice(db, customer, 1000, datetime(2026, 10, 1), status="cancelled")
    for invoice_id in (theirs, paid, cancelled):
        assert _pay(client, customer, 500, [(invoice_id, 500)]).status_code == 400
    assert _state(db, theirs) == ("pending", 0, 1000)
    assert db.query(CustomerPayment).count() == 0


def test_the_same_invoice_twice_or_a_future_date_is_refused(client, admin, customer, three):
    assert _pay(client, customer, 500, [(three[0], 200), (three[0], 300)]).status_code == 422
    tomorrow_plus = (utcnow() + timedelta(days=3)).isoformat() + "Z"
    assert _pay(client, customer, 500, [], received_at=tomorrow_plus).status_code == 400


def test_a_back_dated_payment_keeps_its_date(client, db, admin, customer, three):
    body = _pay(client, customer, 3000, [(three[0], 3000)], received_at="2026-10-20T06:30:00Z").json()
    assert body["received_at"].startswith("2026-10-20T06:30")
    db.expire_all()
    assert db.get(Invoice, three[0]).paid_at == datetime(2026, 10, 20, 6, 30)


def test_deleting_a_payment_undoes_it_and_restoring_brings_it_back_as_credit(client, db, admin, customer, three):
    body = _pay(client, customer, 8000, [(three[0], 3000), (three[1], 3500), (three[2], 1500)]).json()
    res = client.delete(f"/customer-payments/{body['id']}")
    assert res.status_code == 200, res.text
    assert res.json()["reversed_on"] == [f"INV-2026-{i:05d}" for i in three]
    assert _state(db, three[0]) == ("pending", 0, 3000)
    assert _state(db, three[1]) == ("pending", 500, 3500)
    assert _state(db, three[2]) == ("pending", 0, 2500)
    assert db.get(Invoice, three[0]).paid_at is None
    _ledger_matches(db, *three)
    assert client.get(f"/customers/{customer.id}/payments").json() == {"items": [], "credit": 0}

    item = db.query(BinItem).filter_by(item_type="customer_payment").one()
    assert client.post(f"/bin/{item.id}/restore").status_code == 200
    payments = client.get(f"/customers/{customer.id}/payments").json()
    assert payments["credit"] == 8000 and payments["items"][0]["applied_to"] == []
    # Restoring doesn't silently re-pay anything.
    assert _state(db, three[0]) == ("pending", 0, 3000)
    _ledger_matches(db, *three)


def test_cancelling_an_invoice_gives_its_share_back_as_credit(client, db, admin, customer, three):
    body = _pay(client, customer, 4000, [(three[0], 3000), (three[2], 1000)]).json()
    res = client.patch(f"/invoices/{three[2]}", json={"status": "cancelled"})
    assert res.status_code == 200, res.text
    assert _state(db, three[2])[0] == "cancelled"
    assert client.get(f"/customers/{customer.id}/payments").json()["credit"] == 1000
    assert _state(db, three[0]) == ("paid", 3000, 0)
    _ledger_matches(db, *three)
    assert body["id"]


def test_the_statement_shows_the_payment_once_and_the_credit(client, db, admin, customer, three):
    _pay(client, customer, 5000, [(three[0], 3000), (three[1], 1000)], received_at="2026-11-02T05:00:00Z")
    statement = client.get(f"/customers/{customer.id}/statement").json()
    assert statement["credit"] == 1000
    assert [(p["amount"], p["applied_to"], p["unused"]) for p in statement["payments"]] == [
        (5000, [f"INV-2026-{three[0]:05d}", f"INV-2026-{three[1]:05d}"], 1000)
    ]
    # A period before the payment doesn't list it, but credit is still what they have now.
    earlier = client.get(f"/customers/{customer.id}/statement", params={"date_to": "2026-10-31T00:00:00Z"}).json()
    assert earlier["payments"] == [] and earlier["credit"] == 1000


def test_payments_are_for_admins(client, db, customer, three):
    _sign_in(client, db, "ravi", UserRole.USER)
    assert client.get(f"/customers/{customer.id}/payments").status_code == 403
    assert client.get(f"/customers/{customer.id}/open-invoices").status_code == 403
    assert _pay(client, customer, 100, []).status_code == 403
    assert client.delete("/customer-payments/1").status_code == 403


def test_a_missing_customer_or_payment_is_not_found(client, admin):
    assert client.get("/customers/999/payments").status_code == 404
    assert client.post("/customers/999/payments", json={"amount": 1, "payment_method": "Cash"}).status_code == 404
    assert client.post("/customer-payments/999/apply", json={"allocations": [{"invoice_id": 1, "amount": 1}]}).status_code == 404
    assert client.delete("/customer-payments/999").status_code == 404
