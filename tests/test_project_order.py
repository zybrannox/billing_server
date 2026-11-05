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


def _due(db, label, days_from_now, **kw):
    return _project(db, label, status=kw.pop("status", "In Progress"), scheduled_days_ago=-days_from_now, **kw)


def _ordered(db, order):
    items, _ = get_all_projects(db, page_size=50, order=order)
    return [p.project_type for p in items]


def _board(db):
    return _ordered(db, "status_delivery")


def test_board_runs_in_progress_then_pending_then_completed(db):
    _due(db, "completed", 5, status="Completed")
    _due(db, "pending", 0, status="Pending")
    _due(db, "in-progress", -5, status="In Progress")
    assert _board(db) == ["in-progress", "pending", "completed"]


def test_board_runs_today_then_yesterday_and_so_on_within_a_status(db):
    _due(db, "last-week", -7)
    _due(db, "today", 0)
    _due(db, "last-month", -30)
    _due(db, "yesterday", -1)
    assert _board(db) == ["today", "yesterday", "last-week", "last-month"]


def test_board_puts_upcoming_deliveries_above_today(db):
    _due(db, "today", 0)
    _due(db, "next-week", 7)
    _due(db, "tomorrow", 1)
    assert _board(db) == ["next-week", "tomorrow", "today"]


def test_board_orders_every_status_group_by_date(db):
    for status in ("Completed", "Pending", "In Progress"):
        _due(db, f"{status}-older", -3, status=status)
        _due(db, f"{status}-today", 0, status=status)
    assert _board(db) == [
        "In Progress-today", "In Progress-older",
        "Pending-today", "Pending-older",
        "Completed-today", "Completed-older",
    ]


def test_board_orders_completed_by_delivery_date_whether_or_not_delivered(db):
    _due(db, "delivered-due-old", -9, status="Completed", delivered_days_ago=0)
    _due(db, "waiting-due-today", 0, status="Completed")
    _due(db, "delivered-due-yesterday", -1, status="Completed", delivered_days_ago=1)
    assert _board(db) == ["waiting-due-today", "delivered-due-yesterday", "delivered-due-old"]


def test_priority_does_not_outrank_status_or_date_on_the_board(db):
    _due(db, "old-urgent", -5, priority="Urgent")
    _due(db, "today-low", 0, priority="Low")
    _due(db, "pending-urgent", 3, status="Pending", priority="Urgent")
    assert _board(db) == ["today-low", "old-urgent", "pending-urgent"]


def test_pinned_projects_stay_on_top_of_the_board(db):
    _due(db, "in-progress", 0)
    _due(db, "pinned-completed-old", -40, status="Completed", pinned=True)
    assert _board(db) == ["pinned-completed-old", "in-progress"]


def test_same_delivery_time_falls_back_to_priority(db):
    when = utcnow()
    for label, priority in (("normal", "Normal"), ("urgent", "Urgent")):
        db.add(Project(project_type=label, assigned_to="a", priority=priority, client_status="Confirmed",
                       print_status="In Progress", start_date=when, delivery_date=when))
    db.commit()
    assert _board(db) == ["urgent", "normal"]


def test_board_order_holds_across_pages(db):
    for days in (-5, -1, -4, -2, -3):
        _due(db, f"{-days}-days-ago", days)
    first, _ = get_all_projects(db, page=1, page_size=2, order="status_delivery")
    second, _ = get_all_projects(db, page=2, page_size=2, order="status_delivery")
    assert [p.project_type for p in first + second] == ["1-days-ago", "2-days-ago", "3-days-ago", "4-days-ago"]


def test_the_api_rejects_an_unknown_order(client, db):
    from passlib.hash import bcrypt

    from app.entities import User, UserRole
    from app.security import create_access_token

    db.add(User(username="alan", email="a@example.com", phone="9876543210",
                hashed_password=bcrypt.hash("x" * 12), role=UserRole.ADMIN, is_active=True))
    db.commit()
    client.cookies.set("access_token", create_access_token({"sub": "alan", "role": "admin", "tv": 0}))
    assert client.get("/projects/?order=status_delivery").status_code == 200
    assert client.get("/projects/?order=nonsense").status_code == 422
