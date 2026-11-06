"""Adding a project: a new customer can be typed in, and the catch-all customer is gone."""
from datetime import datetime

import pytest
from passlib.hash import bcrypt

from app.datetime_utils import utcnow
from app.entities import Customer, User, UserRole
from app.entities.project import Project
from app.security import create_access_token


@pytest.fixture
def employee(client, db):
    user = User(username="ravi", email="ravi@example.com", phone="9000000001",
                hashed_password=bcrypt.hash("x" * 12), role=UserRole.USER, is_active=True, permissions=[])
    db.add(user)
    db.commit()
    client.cookies.set("access_token", create_access_token({"sub": "ravi", "role": "user", "tv": 0}))
    client.headers["X-Requested-With"] = "XMLHttpRequest"
    return user


def _customer(db, first="Meera", last="S", phone="9876543210", placeholder=False):
    customer = Customer(first_name=first, last_name=last, contact_number=phone, is_placeholder=placeholder)
    db.add(customer)
    db.commit()
    return customer


def _payload(**kw):
    now = utcnow().isoformat() + "Z"
    return {"project_type": "Flex", "assigned_to": "ravi", "client_status": "Confirmed",
            "start_date": now, "delivery_date": now, **kw}


def _new(name="Meera Suresh", phone="9876543210"):
    return {"new_customer": {"name": name, "contact_number": phone}}


def test_a_new_customer_is_created_with_the_project(client, db, employee):
    res = client.post("/projects/", json=_payload(**_new()))
    assert res.status_code == 200, res.text
    customer = db.get(Customer, res.json()["customer_id"])
    assert (customer.first_name, customer.last_name, customer.contact_number) == ("Meera", "Suresh", "9876543210")
    assert res.json()["customer_name"] == "Meera Suresh"


def test_a_single_name_is_enough(client, db, employee):
    res = client.post("/projects/", json=_payload(**_new(name="  Bruce  ")))
    customer = db.get(Customer, res.json()["customer_id"])
    assert (customer.first_name, customer.last_name) == ("Bruce", "")
    assert customer.is_placeholder is False


def test_extra_words_stay_in_the_last_name(client, db, employee):
    res = client.post("/projects/", json=_payload(**_new(name="Anies  Decors   Kochi")))
    customer = db.get(Customer, res.json()["customer_id"])
    assert (customer.first_name, customer.last_name) == ("Anies", "Decors Kochi")


def test_spaces_and_dashes_in_a_phone_number_are_fine(client, db, employee):
    res = client.post("/projects/", json=_payload(**_new(phone="+91 98765-43210")))
    assert db.get(Customer, res.json()["customer_id"]).contact_number == "+919876543210"


@pytest.mark.parametrize("phone", ["12345", "not a phone", "", "1234567890123456"])
def test_a_bad_phone_number_is_refused_and_nothing_is_created(client, db, employee, phone):
    assert client.post("/projects/", json=_payload(**_new(phone=phone))).status_code == 422
    assert db.query(Customer).count() == 0
    assert db.query(Project).count() == 0


def test_a_blank_name_is_refused(client, db, employee):
    assert client.post("/projects/", json=_payload(**_new(name="   "))).status_code == 422


def test_the_same_person_isnt_added_twice(client, db, employee):
    existing = _customer(db, "Meera", "Suresh")
    res = client.post("/projects/", json=_payload(**_new(name="meera  SURESH")))
    assert res.json()["customer_id"] == existing.id
    assert db.query(Customer).count() == 1


def test_a_shared_phone_number_with_another_name_is_a_new_customer(client, db, employee):
    existing = _customer(db, "Meera", "Suresh")
    res = client.post("/projects/", json=_payload(**_new(name="Ravi Kumar")))
    assert res.json()["customer_id"] != existing.id
    assert db.query(Customer).count() == 2


def test_a_project_cant_have_both_kinds_of_customer(client, db, employee):
    existing = _customer(db)
    assert client.post("/projects/", json=_payload(customer_id=existing.id, **_new())).status_code == 422


def test_picking_an_existing_customer_still_works(client, db, employee):
    existing = _customer(db)
    assert client.post("/projects/", json=_payload(customer_id=existing.id)).json()["customer_id"] == existing.id


def test_a_new_project_cant_use_the_catch_all_customer(client, db, employee):
    unknown = _customer(db, "UNKOWN", " NAME", "9999999999", placeholder=True)
    res = client.post("/projects/", json=_payload(customer_id=unknown.id))
    assert res.status_code == 400
    assert db.query(Project).count() == 0


def test_the_project_form_isnt_offered_the_catch_all_customer(client, db, employee):
    _customer(db)
    _customer(db, "UNKOWN", " NAME", "9999999999", placeholder=True)
    names = [c["first_name"] for c in client.get("/customers/", params={"exclude_placeholders": "true"}).json()["items"]]
    assert names == ["Meera"]


def test_everywhere_else_still_lists_the_catch_all_customer(client, db, employee):
    _customer(db, "UNKOWN", " NAME", "9999999999", placeholder=True)
    assert client.get("/customers/").json()["total"] == 1


@pytest.mark.parametrize("sent,stored", [
    ("2026-11-06T10:30:00.000Z", datetime(2026, 11, 6, 10, 30)),
    ("2026-11-06T10:30:00+05:30", datetime(2026, 11, 6, 5, 0)),
])
def test_project_dates_are_stored_as_utc(client, db, employee, sent, stored):
    res = client.post("/projects/", json=_payload(start_date=sent, delivery_date=sent, **_new()))
    assert res.status_code == 200, res.text
    project = db.get(Project, res.json()["id"])
    assert (project.start_date, project.delivery_date) == (stored, stored)


def test_older_projects_keep_the_catch_all_customer(client, db, employee):
    unknown = _customer(db, "UNKOWN", " NAME", "9999999999", placeholder=True)
    now = utcnow()
    project = Project(project_type="Flex", assigned_to="ravi", priority="Normal", client_status="Confirmed", print_status="In Progress",
                      start_date=now, delivery_date=now, customer_id=unknown.id)
    db.add(project)
    db.commit()
    assert client.put(f"/projects/{project.id}", json={"description": "Changed"}).status_code == 200
    db.refresh(project)
    assert project.customer_id == unknown.id
