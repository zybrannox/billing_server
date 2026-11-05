"""Priority is no longer asked for or shown anywhere, but what's already stored
must survive, and everything that used to require it must keep working."""
from datetime import timedelta

import pytest
from passlib.hash import bcrypt

from app.dashboard.model import AttentionProject, DashboardSummary
from app.dashboard.repository import get_attention_projects
from app.datetime_utils import utcnow
from app.entities import User, UserRole
from app.entities.project import Project
from app.projects.model import ProjectCreate
from app.quotations.model import QuotationConvertRequest


@pytest.fixture
def logged_in(client, db):
    from app.security import create_access_token

    db.add(User(username="alan", email="a@example.com", phone="9876543210",
                hashed_password=bcrypt.hash("x" * 12), role=UserRole.ADMIN, is_active=True))
    db.commit()
    client.cookies.set("access_token", create_access_token({"sub": "alan", "role": "admin", "tv": 0}))
    client.headers["X-Requested-With"] = "XMLHttpRequest"


def _project(db, priority="Normal", days_from_now=5, **kw):
    now = utcnow()
    p = Project(project_type="Flex", assigned_to="a", priority=priority, client_status="Confirmed",
                print_status="In Progress", start_date=now, delivery_date=now + timedelta(days=days_from_now), **kw)
    db.add(p)
    db.commit()
    return p


def test_a_new_project_without_a_priority_is_normal():
    # On the schema: creating through the API needs Postgres, which accepts
    # project.dict()'s ISO date strings where this SQLite test database won't.
    now = utcnow()
    body = ProjectCreate(project_type="Flex", assigned_to="a", client_status="Confirmed", start_date=now, delivery_date=now)
    assert body.dict()["priority"] == "Normal"


def test_editing_a_project_leaves_its_stored_priority_alone(client, logged_in, db):
    project = _project(db, priority="Urgent")
    assert client.put(f"/projects/{project.id}", json={"description": "edited"}).status_code == 200
    db.refresh(project)
    assert project.description == "edited"
    assert project.priority == "Urgent"


def test_a_quotation_can_be_converted_without_a_priority():
    now = utcnow()
    body = QuotationConvertRequest(assigned_to="a", client_status="Confirmed", start_date=now, delivery_date=now)
    assert body.priority == "Normal"


def test_dashboard_attention_is_about_lateness_not_a_hidden_priority(db):
    overdue = _project(db, days_from_now=-1)
    _project(db, priority="Urgent", days_from_now=5)
    assert [p.id for p in get_attention_projects(db)] == [overdue.id]


def test_dashboard_no_longer_reports_priority():
    # By its schema: the summary endpoint itself needs Postgres (date_trunc).
    assert "priority_breakdown" not in DashboardSummary.model_fields
    assert "priority" not in AttentionProject.model_fields
