import pytest

from app import ttl_cache
from app.datetime_utils import utcnow
from app.entities import User, UserRole
from app.entities.project import Project
from app.invoices.model import InvoiceCreate, InvoiceItemCreate
from app.invoices.repository import create_invoice, get_latest_invoice_statuses
from app.security import create_access_token
from passlib.hash import bcrypt


def test_ttl_cache_serves_then_expires_and_clears():
    calls = []
    compute = lambda: calls.append(1) or len(calls)
    assert ttl_cache.get_or_compute("k", compute, ttl=60) == 1
    assert ttl_cache.get_or_compute("k", compute, ttl=60) == 1
    ttl_cache.clear()
    assert ttl_cache.get_or_compute("k", compute, ttl=60) == 2
    assert ttl_cache.get_or_compute("k", compute, ttl=0) == 3  # ttl 0 = never cached


def test_a_value_computed_before_a_clear_is_not_stored_after_it():
    def compute_while_a_write_lands():
        ttl_cache.clear()  # a write finishes mid-computation
        return "stale"

    assert ttl_cache.get_or_compute("k", compute_while_a_write_lands, ttl=60) == "stale"
    assert ttl_cache.get_or_compute("k", lambda: "fresh", ttl=60) == "fresh"


def _project(db):
    project = Project(project_type="Flex", assigned_to="a", priority="Normal", client_status="Confirmed",
                      start_date=utcnow(), delivery_date=utcnow())
    db.add(project)
    db.commit()
    return project


def test_latest_invoice_statuses_picks_the_newest_per_project_in_one_query(db):
    p1, p2, p3 = _project(db), _project(db), _project(db)
    items = [InvoiceItemCreate(description="x", width=1, height=1, rate=10, pieces=1, unit="ft")]
    first = create_invoice(db, InvoiceCreate(project_id=p1.id, items=items), "t")
    first.status = "cancelled"
    db.commit()
    create_invoice(db, InvoiceCreate(project_id=p1.id, items=items), "t")  # newer, pending
    create_invoice(db, InvoiceCreate(project_id=p2.id, items=items), "t")
    assert get_latest_invoice_statuses(db, [p1.id, p2.id, p3.id]) == {p1.id: "pending", p2.id: "pending"}
    assert get_latest_invoice_statuses(db, []) == {}


def test_delivery_notifications_are_cached_until_a_write_clears_them(client, db):
    admin = User(username="boss", email="b@example.com", phone="9876543211",
                 hashed_password=bcrypt.hash("x" * 12), role=UserRole.ADMIN, is_active=True)
    db.add(admin)
    db.commit()
    client.cookies.set("access_token", create_access_token({"sub": "boss", "role": "admin"}))
    headers = {"X-Requested-With": "test"}
    url = "/dashboard/notifications/deliveries"

    assert client.get(url).json() == []
    delivered = _project(db)
    delivered.delivered_at = utcnow()
    delivered.delivered_by = "alan"
    db.commit()  # written behind the API's back: the cache still holds the empty list
    assert client.get(url).json() == []
    # a failed write does not clear it ...
    assert client.patch("/invoices/999999/mark-paid", headers=headers, json={"payment_method": "Cash"}).status_code == 404
    assert client.get(url).json() == []
    # ... a successful one does
    assert client.post("/projects/bulk-delete", headers=headers, json={"ids": []}).status_code < 400
    assert [d["id"] for d in client.get(url).json()] == [delivered.id]
