"""Any staff member can deliver unpaid work on credit, and it stays flagged."""
from datetime import datetime

import pytest
from passlib.hash import bcrypt

from app.entities import Invoice, User, UserRole
from app.entities.project import Project
from app.security import create_access_token


@pytest.fixture
def employee(client, db):
    db.add(User(username="ravi", email="ravi@example.com", phone="9000000001",
                hashed_password=bcrypt.hash("x" * 12), role=UserRole.USER, is_active=True, permissions=[]))
    db.commit()
    client.cookies.set("access_token", create_access_token({"sub": "ravi", "role": "user", "tv": 0}))
    client.headers["X-Requested-With"] = "XMLHttpRequest"


def _ready(db, status="pending", designed=True, printed=True):
    on = datetime(2026, 11, 1)
    project = Project(project_type="Flex", assigned_to="ravi", priority="Normal", client_status="Confirmed",
                      print_status="Completed" if printed else "In Progress", start_date=on, delivery_date=on,
                      design_completed_at=on if designed else None)
    db.add(project)
    db.flush()
    db.add(Invoice(project_id=project.id, status=status, subtotal=500, discount_amount=0, amount=500, advance_amount=0, created_at=on))
    db.commit()
    return project


def _deliver(client, project, on_credit=False):
    return client.patch(f"/projects/{project.id}/delivered", params={"on_credit": on_credit})


def test_an_employee_can_deliver_on_credit(client, db, employee):
    project = _ready(db)
    res = _deliver(client, project, on_credit=True)
    assert res.status_code == 200, res.text
    db.refresh(project)
    assert (project.delivered_on_credit, project.delivered_by) == (True, "ravi")
    assert project.delivered_at is not None


def test_the_unpaid_invoice_stays_unpaid(client, db, employee):
    project = _ready(db)
    _deliver(client, project, on_credit=True)
    assert db.query(Invoice).one().status == "pending"


def test_a_credit_delivery_stays_flagged_for_follow_up(client, db, employee):
    from app.dashboard.repository import get_attention_projects

    project = _ready(db)
    _deliver(client, project, on_credit=True)
    assert [p.id for p in get_attention_projects(db)] == [project.id]


def test_without_credit_it_still_has_to_be_paid(client, db, employee):
    project = _ready(db)
    assert _deliver(client, project).status_code == 400
    db.refresh(project)
    assert project.delivered_at is None


def test_a_paid_order_is_delivered_normally(client, db, employee):
    project = _ready(db, status="paid")
    assert _deliver(client, project).status_code == 200
    db.refresh(project)
    assert project.delivered_on_credit is False


@pytest.mark.parametrize("status", ["paid", "cancelled"])
def test_credit_only_applies_to_an_unpaid_invoice(client, db, employee, status):
    project = _ready(db, status=status)
    assert _deliver(client, project, on_credit=True).status_code == 400


@pytest.mark.parametrize("designed,printed", [(False, True), (True, False)])
def test_credit_doesnt_skip_design_or_printing(client, db, employee, designed, printed):
    project = _ready(db, designed=designed, printed=printed)
    assert _deliver(client, project, on_credit=True).status_code == 400


def test_an_order_with_no_invoice_cant_go_on_credit(client, db, employee):
    on = datetime(2026, 11, 1)
    project = Project(project_type="Flex", assigned_to="ravi", priority="Normal", client_status="Confirmed",
                      print_status="Completed", start_date=on, delivery_date=on, design_completed_at=on)
    db.add(project)
    db.commit()
    assert _deliver(client, project, on_credit=True).status_code == 400


def test_delivering_needs_a_login(client, db):
    project = _ready(db)
    client.headers["X-Requested-With"] = "XMLHttpRequest"
    assert _deliver(client, project, on_credit=True).status_code == 401
