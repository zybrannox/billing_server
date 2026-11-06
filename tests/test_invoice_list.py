"""Finding an invoice fast: search, views, the payment summary, and who may look."""
from datetime import timedelta

import pytest
from passlib.hash import bcrypt

from app.datetime_utils import utcnow
from app.entities import Customer, User, UserRole
from app.entities.project import Project
from app.invoices.model import InvoiceCreate, InvoiceItemCreate
from app.invoices.repository import create_invoice
from app.security import create_access_token

LINE = {"description": "Banner", "width": 1, "height": 1, "rate": 100, "pieces": 1, "unit": "ft"}


def _sign_in(client, db, name, role=UserRole.USER, permissions=()):
    user = User(username=name, email=f"{name}@example.com", phone="9" + str(abs(hash(name)))[:9].zfill(9),
                hashed_password=bcrypt.hash("x" * 12), role=role, is_active=True, permissions=list(permissions))
    db.add(user)
    db.commit()
    client.cookies.set("access_token", create_access_token({"sub": name, "role": role.value, "tv": 0}))
    client.headers["X-Requested-With"] = "XMLHttpRequest"


@pytest.fixture
def admin(client, db):
    _sign_in(client, db, "boss", UserRole.ADMIN)


def _invoice(db, first="Asha", last="Rao", phone="9876500001", job="Flex", due=None, status=None, advance=0):
    customer = Customer(first_name=first, last_name=last, contact_number=phone)
    db.add(customer)
    db.flush()
    now = utcnow()
    project = Project(project_type=job, customer_id=customer.id, assigned_to="t", priority="Normal",
                      client_status="Confirmed", print_status="In Progress", start_date=now, delivery_date=now)
    db.add(project)
    db.commit()
    invoice = create_invoice(db, InvoiceCreate(project_id=project.id, items=[InvoiceItemCreate(**LINE)]), "t")
    invoice.due_date = due
    invoice.advance_amount = advance
    if status:
        invoice.status = status
    db.commit()
    return invoice


def _numbers(client, **params):
    res = client.get("/invoices/", params=params)
    assert res.status_code == 200, res.text
    return [i["invoice_number"] for i in res.json()["items"]]


@pytest.mark.parametrize("term", ["Asha", "asha rao", "98765", "flex", "  Rao  "])
def test_search_finds_an_invoice_by_what_you_know(client, db, admin, term):
    invoice = _invoice(db)
    _invoice(db, "Vikram", "Shah", "9000000002", "Cards")
    assert _numbers(client, search=term) == [invoice.invoice_number]


def test_search_finds_it_by_its_number(client, db, admin):
    invoice = _invoice(db)
    _invoice(db, "Vikram", "Shah", "9000000002", "Cards")
    assert _numbers(client, search=invoice.invoice_number.lower()) == [invoice.invoice_number]


def test_a_blank_search_finds_everything(client, db, admin):
    _invoice(db)
    assert len(_numbers(client, search="   ")) == 1


def test_views_separate_what_is_owed_from_what_is_settled(client, db, admin):
    now = utcnow()
    late = _invoice(db, due=now - timedelta(days=2))
    upcoming = _invoice(db, due=now + timedelta(days=5))
    paid = _invoice(db, status="paid", due=now - timedelta(days=2))
    cancelled = _invoice(db, status="cancelled")
    assert set(_numbers(client, view="unpaid")) == {late.invoice_number, upcoming.invoice_number}
    assert _numbers(client, view="overdue") == [late.invoice_number]
    assert _numbers(client, view="paid") == [paid.invoice_number]
    assert _numbers(client, view="cancelled") == [cancelled.invoice_number]
    assert len(_numbers(client)) == 4


def test_an_unknown_view_is_refused(client, db, admin):
    assert client.get("/invoices/", params={"view": "nonsense"}).status_code == 422


def test_summary_adds_up_balances_not_invoice_totals(client, db, admin):
    now = utcnow()
    _invoice(db, due=now - timedelta(days=1), advance=40)  # 60 owed, overdue
    _invoice(db, due=now + timedelta(minutes=1))  # 100 owed, due today
    _invoice(db, due=now + timedelta(days=10))  # 100 owed, within 30 days
    _invoice(db, due=now + timedelta(days=60))  # 100 owed, later
    _invoice(db)  # 100 owed, no due date
    _invoice(db, status="paid", due=now - timedelta(days=1))
    _invoice(db, status="cancelled", due=now - timedelta(days=1))
    summary = client.get("/invoices/summary").json()
    assert summary["total_outstanding"] == 460
    assert summary["overdue"] == 60
    assert summary["due_within_30_days"] == 200
    assert summary["counts"] == {"all": 7, "unpaid": 5, "overdue": 1, "paid": 1, "cancelled": 1}


def test_due_today_ends_at_midnight_where_the_shop_is(client, db, admin):
    now = utcnow()
    # Just after the shop's midnight tonight, whichever offset the shop is at.
    offset = timedelta(minutes=330)
    midnight = (now + offset).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1) - offset
    _invoice(db, due=midnight + timedelta(minutes=5))
    assert client.get("/invoices/summary", params={"tz_offset_minutes": 330}).json()["due_today"] == 0


def test_an_advance_bigger_than_the_invoice_owes_nothing(client, db, admin):
    _invoice(db, advance=500)
    assert client.get("/invoices/summary").json()["total_outstanding"] == 0


@pytest.mark.parametrize("permissions", [(), ("workspace.manage",), ("invoice.edit",), ("notes.access",)])
def test_only_admins_can_browse_invoices(client, db, permissions):
    _sign_in(client, db, "ravi", permissions=permissions)
    assert client.get("/invoices/").status_code == 403
    assert client.get("/invoices/summary").status_code == 403


def test_customer_list_says_how_many_invoices_each_has(client, db, admin):
    invoice = _invoice(db)
    customer_id = invoice.project.customer_id
    rows = {c["id"]: c for c in client.get("/customers/").json()["items"]}
    assert rows[customer_id]["invoice_count"] == 1


@pytest.mark.parametrize("term", ["%", "_"])
def test_search_treats_wildcards_as_plain_characters(client, db, admin, term):
    _invoice(db)
    assert _numbers(client, search=term) == []


def test_changing_the_status_of_a_missing_invoice_is_not_found(client, db, admin):
    assert client.patch("/invoices/999999", json={"status": "cancelled"}).status_code == 404


def test_a_billed_note_keeps_its_link_when_its_invoice_is_restored(client, db, admin):
    invoice = _invoice(db)
    note = client.post("/notes/", json={"text": "Flex"}).json()
    from app.entities import Note
    db.get(Note, note["id"]).invoice_id = invoice.id
    db.commit()
    assert client.delete(f"/invoices/{invoice.id}").status_code == 200
    assert client.get("/notes/").json()["items"][0]["invoice_id"] is None
    item = client.get("/bin/").json()["items"][0]
    assert client.post(f"/bin/{item['id']}/restore").status_code == 200
    assert client.get("/notes/").json()["items"][0]["invoice_id"] == invoice.id
