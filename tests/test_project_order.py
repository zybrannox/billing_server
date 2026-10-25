from datetime import timedelta

from app.datetime_utils import utcnow
from app.entities.project import Project
from app.projects.repository import get_all_projects


def _project(db, label, status="Completed", delivered_days_ago=None, scheduled_days_ago=0, priority="Normal", pinned=False):
    now = utcnow()
    p = Project(
        project_type=label, assigned_to="a", priority=priority, client_status="Confirmed", print_status=status,
        start_date=now, delivery_date=now - timedelta(days=scheduled_days_ago), pinned=pinned,
        delivered_at=None if delivered_days_ago is None else now - timedelta(days=delivered_days_ago),
    )
    db.add(p)
    db.commit()
    return p


def _order(db):
    items, _ = get_all_projects(db, page_size=50)
    return [p.project_type for p in items]


def test_delivered_projects_run_newest_delivery_first(db):
    _project(db, "delivered-last-week", delivered_days_ago=7)
    _project(db, "delivered-yesterday", delivered_days_ago=1)
    _project(db, "delivered-last-month", delivered_days_ago=30)
    assert _order(db) == ["delivered-yesterday", "delivered-last-week", "delivered-last-month"]


def test_priority_does_not_outrank_delivery_among_delivered(db):
    _project(db, "old-but-urgent", priority="Urgent", delivered_days_ago=20)
    _project(db, "recent-low", priority="Low", delivered_days_ago=1)
    assert _order(db) == ["recent-low", "old-but-urgent"]


def test_waiting_for_delivery_comes_first_then_delivered_ones_below(db):
    _project(db, "delivered-just-now", delivered_days_ago=0)
    _project(db, "waiting-due-later", scheduled_days_ago=-2)
    _project(db, "waiting-overdue", scheduled_days_ago=9)
    _project(db, "delivered-last-week", delivered_days_ago=7)
    assert _order(db) == ["waiting-overdue", "waiting-due-later", "delivered-just-now", "delivered-last-week"]


def test_other_statuses_and_pinning_are_unchanged(db):
    _project(db, "completed-new", delivered_days_ago=0)
    _project(db, "progress-normal", status="In Progress", priority="Normal")
    _project(db, "progress-urgent", status="In Progress", priority="Urgent")
    _project(db, "pending", status="Pending")
    _project(db, "completed-pinned", delivered_days_ago=40, pinned=True)
    assert _order(db) == ["completed-pinned", "pending", "progress-urgent", "progress-normal", "completed-new"]
