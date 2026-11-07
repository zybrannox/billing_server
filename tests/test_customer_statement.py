"""A customer statement lists their bills over a period with what's paid and owed."""
from datetime import datetime

import pytest
from passlib.hash import bcrypt

from app.entities import Customer, Invoice, User, UserRole
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


@pytest.fixture
def customer(db):
    row = Customer(first_name="Meera", last_name="S", contact_number="9876543210")
    db.add(row)
    db.commit()
    return row


def _invoice(db, customer, amount, status="pending", advance=0, on=datetime(2026, 10, 15), job="Flex"):
    project = Project(project_type=job, assigned_to="boss", priority="Normal", client_status="Confirmed",
                      print_status="Completed", start_date=on, delivery_date=on, customer_id=customer.id)
    db.add(project)
    db.flush()
    invoice = Invoice(project_id=project.id, status=status, subtotal=amount, discount_amount=0, amount=amount,
                      advance_amount=advance, created_at=on)
    db.add(invoice)
    db.flush()
    invoice.invoice_number = f"INV-2026-{invoice.id:05d}"
    db.commit()
    return invoice


def _statement(client, customer, **params):
    res = client.get(f"/customers/{customer.id}/statement", params=params)
    assert res.status_code == 200, res.text
    return res.json()


def test_a_statement_needs_an_admin(client, db, customer):
    assert client.get(f"/customers/{customer.id}/statement").status_code == 401
    _sign_in(client, db, "ravi", UserRole.USER)
    assert client.get(f"/customers/{customer.id}/statement").status_code == 403


def test_a_missing_customer_is_not_found(client, admin):
    assert client.get("/customers/999/statement").status_code == 404


def test_it_lists_bills_with_what_is_paid_and_owed(client, db, admin, customer):
    _invoice(db, customer, 1000, status="paid", on=datetime(2026, 10, 1))
    _invoice(db, customer, 500, advance=200, on=datetime(2026, 10, 5), job="Gift")
    _invoice(db, customer, 300, on=datetime(2026, 10, 9))
    body = _statement(client, customer)
    assert [(r["amount"], r["paid"], r["balance"], r["status"]) for r in body["rows"]] == [
        (1000, 1000, 0, "paid"),
        (500, 200, 300, "pending"),
        (300, 0, 300, "pending"),
    ]
    assert body["rows"][1]["job"] == "Gift"
    assert (body["total_billed"], body["total_paid"], body["total_balance"], body["total_outstanding"]) == (1800, 1200, 600, 600)
    assert body["customer"]["first_name"] == "Meera"


def test_cancelled_bills_are_left_out(client, db, admin, customer):
    _invoice(db, customer, 1000, status="cancelled")
    _invoice(db, customer, 300)
    body = _statement(client, customer)
    assert [r["amount"] for r in body["rows"]] == [300]
    assert body["total_outstanding"] == 300


def test_a_period_limits_the_rows_but_not_what_is_owed_overall(client, db, admin, customer):
    _invoice(db, customer, 400, on=datetime(2026, 9, 20))
    _invoice(db, customer, 300, on=datetime(2026, 10, 1))
    _invoice(db, customer, 200, on=datetime(2026, 10, 31, 23, 59))
    _invoice(db, customer, 100, on=datetime(2026, 11, 1))
    body = _statement(client, customer, date_from="2026-10-01T00:00:00Z", date_to="2026-11-01T00:00:00Z")
    assert [r["amount"] for r in body["rows"]] == [300, 200]
    assert body["total_balance"] == 500
    assert body["total_outstanding"] == 1000
    assert body["date_from"].startswith("2026-10-01")


def test_period_edges_follow_the_time_zone_sent(client, db, admin, customer):
    # Midnight in India on 1 Oct is 18:30 UTC on 30 Sep.
    _invoice(db, customer, 300, on=datetime(2026, 9, 30, 19, 0))
    body = _statement(client, customer, date_from="2026-10-01T00:00:00+05:30")
    assert [r["amount"] for r in body["rows"]] == [300]


def test_only_this_customers_bills(client, db, admin, customer):
    other = Customer(first_name="Ravi", last_name="K", contact_number="9876500000")
    db.add(other)
    db.commit()
    _invoice(db, other, 999)
    _invoice(db, customer, 300)
    assert [r["amount"] for r in _statement(client, customer)["rows"]] == [300]


def test_a_customer_with_no_bills_gets_an_empty_statement(client, db, admin, customer):
    body = _statement(client, customer)
    assert (body["rows"], body["total_billed"], body["total_outstanding"]) == ([], 0, 0)


def test_bills_created_on_their_own_are_included(client, db, admin, customer):
    res = client.post("/invoices/", json={
        "new_project": {"customer_id": customer.id},
        "items": [{"description": "Banner", "width": 8, "height": 4, "rate": 10, "pieces": 1, "unit": "ft"}],
    })
    assert res.status_code == 200, res.text
    assert [r["invoice_number"] for r in _statement(client, customer)["rows"]] == [res.json()["invoice_number"]]
    assert db.query(Project).one().bill_only is True
