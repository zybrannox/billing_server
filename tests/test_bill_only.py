"""A bill created on its own is just a bill: it never shows up as a project."""
import pytest
from passlib.hash import bcrypt

from app.dashboard import repository as dashboard
from app.datetime_utils import utcnow
from app.entities import Customer, Invoice, User, UserRole
from app.entities.project import Project
from app.security import create_access_token

LINE = {"description": "Banner", "width": 8, "height": 4, "rate": 10, "pieces": 2, "unit": "ft"}


@pytest.fixture
def admin(client, db):
    user = User(username="boss", email="boss@example.com", phone="9000000001",
                hashed_password=bcrypt.hash("x" * 12), role=UserRole.ADMIN, is_active=True, permissions=[])
    db.add(user)
    db.commit()
    client.cookies.set("access_token", create_access_token({"sub": "boss", "role": "admin", "tv": 0}))
    client.headers["X-Requested-With"] = "XMLHttpRequest"
    return user


@pytest.fixture
def customer(db):
    row = Customer(first_name="Meera", last_name="S", contact_number="9876543210")
    db.add(row)
    db.commit()
    return row


def _bill(client, customer):
    res = client.post("/invoices/", json={"new_project": {"project_type": "Flex", "customer_id": customer.id}, "items": [LINE]})
    assert res.status_code == 200, res.text
    return res.json()


def _project(db, customer, assigned_to="boss"):
    now = utcnow()
    project = Project(project_type="Flex", assigned_to=assigned_to, priority="Normal", client_status="Confirmed",
                      print_status="In Progress", start_date=now, delivery_date=now, customer_id=customer.id)
    db.add(project)
    db.commit()
    return project


def test_a_bill_isnt_listed_as_a_project(client, db, admin, customer):
    _bill(client, customer)
    assert client.get("/projects/").json()["total"] == 0


def test_a_real_project_is_still_listed(client, db, admin, customer):
    project = _project(db, customer)
    _bill(client, customer)
    assert [p["id"] for p in client.get("/projects/").json()["items"]] == [project.id]


def test_invoicing_a_real_project_leaves_it_visible(client, db, admin, customer):
    project = _project(db, customer)
    res = client.post("/invoices/", json={"project_id": project.id, "items": [LINE]})
    assert res.status_code == 200, res.text
    assert client.get("/projects/").json()["total"] == 1


def test_a_bill_can_be_found_in_every_project_view(client, db, admin, customer):
    _bill(client, customer)
    for params in ({"view": "ongoing"}, {"customer_id": customer.id}, {"assigned_to": "boss"}):
        assert client.get("/projects/", params=params).json()["total"] == 0, params


def test_the_bill_itself_still_works_everywhere(client, db, admin, customer):
    bill = _bill(client, customer)
    assert bill["invoice_number"]
    assert client.get("/invoices/").json()["total"] == 1
    assert client.get(f"/invoices/{bill['id']}/details").status_code == 200
    assert client.get("/invoices/summary").status_code == 200
    assert client.get("/customers/").json()["items"][0]["invoice_count"] == 1


def test_a_bill_can_be_paid(client, db, admin, customer):
    bill = _bill(client, customer)
    res = client.patch(f"/invoices/{bill['id']}/mark-paid", json={"payment_method": "Cash"})
    assert res.status_code == 200, res.text


def test_customer_counts_leave_bills_out(client, db, admin, customer):
    _bill(client, customer)
    _project(db, customer)
    profile = client.get(f"/customers/{customer.id}/profile").json()
    assert len(profile["projects"]) == 1
    assert (profile["stats"]["total_orders"], profile["stats"]["active_orders"]) == (1, 1)


def test_dashboard_counts_leave_bills_out_but_keep_the_money(client, db, admin, customer):
    bill = _bill(client, customer)
    client.patch(f"/invoices/{bill['id']}/mark-paid", json={"payment_method": "Cash"})
    project = _project(db, customer)
    stats = dashboard.get_stats(db)
    assert stats["total_projects"] == 1
    assert stats["total_revenue"] > 0
    assert sum(row["count"] for row in dashboard.get_project_status_breakdown(db)) == 1
    assert [p.id for p in dashboard.get_attention_projects(db)] in ([], [project.id])


def test_a_customer_with_a_deleted_bill_can_still_be_deleted(client, db, admin, customer):
    bill = _bill(client, customer)
    assert client.delete(f"/invoices/{bill['id']}").status_code == 200
    assert db.query(Invoice).count() == 0
    assert client.delete(f"/customers/{customer.id}").status_code == 200
    assert db.query(Project).count() == 0


def test_a_customer_with_a_live_bill_is_protected(client, db, admin, customer):
    _bill(client, customer)
    assert client.delete(f"/customers/{customer.id}").status_code == 400
    assert db.query(Project).count() == 1
