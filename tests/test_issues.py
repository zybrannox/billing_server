"""Employees report issues; admins see them and mark them done; the reporter is told."""
import pytest
from passlib.hash import bcrypt

from app.entities import AuditLog, Issue, User, UserRole
from app.security import create_access_token


def _user(db, name, role=UserRole.USER):
    user = User(username=name, email=f"{name}@example.com", phone=str(9000000000 + abs(hash(name)) % 999999999)[:10],
                hashed_password=bcrypt.hash("x" * 12), role=role, is_active=True, permissions=[])
    db.add(user)
    db.commit()
    return user


def _sign_in(client, user):
    client.cookies.set("access_token", create_access_token({"sub": user.username, "role": user.role.value, "tv": 0}))
    client.headers["X-Requested-With"] = "XMLHttpRequest"


@pytest.fixture
def ravi(client, db):
    user = _user(db, "ravi")
    _sign_in(client, user)
    return user


@pytest.fixture
def boss(db):
    return _user(db, "boss", UserRole.ADMIN)


def _report(client, text="The printer is jammed"):
    res = client.post("/issues/", json={"text": text})
    assert res.status_code == 200, res.text
    return res.json()


def _solve(client, boss, issue_id, reporter=None):
    _sign_in(client, boss)
    res = client.patch(f"/issues/{issue_id}", json={"is_done": True})
    assert res.status_code == 200, res.text
    if reporter:
        _sign_in(client, reporter)
    return res.json()


@pytest.mark.parametrize("method,path", [
    ("post", "/issues/"), ("get", "/issues/"), ("get", "/issues/mine"), ("post", "/issues/mine/seen"), ("patch", "/issues/1"),
])
def test_issues_need_a_login(client, method, path):
    client.headers["X-Requested-With"] = "XMLHttpRequest"
    assert client.request(method.upper(), path, json={}).status_code == 401


def test_any_employee_can_report_an_issue(client, db, ravi):
    issue = _report(client, "  The printer is jammed  ")
    assert (issue["text"], issue["reported_by"], issue["is_done"]) == ("The printer is jammed", "ravi", False)
    assert db.query(Issue).one().reported_by_id == ravi.id


@pytest.mark.parametrize("text", ["", "    "])
def test_a_blank_issue_is_refused(client, db, ravi, text):
    assert client.post("/issues/", json={"text": text}).status_code == 422
    assert db.query(Issue).count() == 0


def test_a_very_long_issue_is_refused(client, ravi):
    assert client.post("/issues/", json={"text": "x" * 2001}).status_code == 422


def test_reporting_is_rate_limited(client, ravi):
    codes = [client.post("/issues/", json={"text": "x"}).status_code for _ in range(31)]
    assert codes == [200] * 30 + [429]


def test_employees_only_see_their_own_issues(client, db, ravi):
    _report(client, "Ravi's problem")
    other = _user(db, "meera")
    _sign_in(client, other)
    _report(client, "Meera's problem")
    assert [i["text"] for i in client.get("/issues/mine").json()["items"]] == ["Meera's problem"]


def test_a_reused_username_doesnt_inherit_issues(client, db, ravi):
    _report(client, "Private problem")
    db.query(Issue).update({Issue.reported_by_id: ravi.id + 1000})
    db.commit()
    assert client.get("/issues/mine").json()["items"] == []


@pytest.mark.parametrize("method,path,body", [
    ("get", "/issues/", None),
    ("patch", "/issues/1", {"is_done": True}),
])
def test_employees_cant_use_the_admin_side(client, db, ravi, method, path, body):
    _report(client)
    assert client.request(method.upper(), path, json=body).status_code == 403
    assert db.query(Issue).one().is_done is False


def test_the_admin_list_shows_who_reported_what_open_first(client, db, ravi, boss):
    first = _report(client, "First")
    _report(client, "Second")
    _solve(client, boss, first["id"])
    body = client.get("/issues/").json()
    assert [i["text"] for i in body["items"]] == ["Second", "First"]
    assert body["items"][0]["reported_by"] == "ravi"
    assert (body["open_count"], body["done_count"], body["total"]) == (1, 1, 2)


def test_the_admin_list_can_be_filtered_and_keeps_both_counts(client, db, ravi, boss):
    first = _report(client, "First")
    _report(client, "Second")
    _solve(client, boss, first["id"])
    done = client.get("/issues/", params={"status": "done"}).json()
    assert [i["text"] for i in done["items"]] == ["First"]
    assert (done["total"], done["open_count"]) == (1, 1)
    assert [i["text"] for i in client.get("/issues/", params={"status": "open"}).json()["items"]] == ["Second"]


def test_marking_done_says_who_and_when_and_is_logged(client, db, ravi, boss):
    issue = _solve(client, boss, _report(client)["id"])
    assert issue["is_done"] is True
    assert issue["done_by"] == "boss"
    assert issue["done_at"] is not None
    assert db.query(AuditLog).filter_by(action="issue.done", actor="boss").count() == 1


def test_a_missing_issue_is_not_found(client, db, boss):
    _sign_in(client, boss)
    assert client.patch("/issues/999", json={"is_done": True}).status_code == 404


def test_nothing_to_notify_until_its_solved(client, ravi):
    _report(client)
    body = client.get("/issues/mine").json()
    assert body["unseen_count"] == 0
    assert body["items"][0]["unseen"] is False


def test_the_reporter_is_notified_when_its_solved(client, db, ravi, boss):
    _solve(client, boss, _report(client)["id"], reporter=ravi)
    body = client.get("/issues/mine").json()
    assert body["unseen_count"] == 1
    assert body["items"][0]["unseen"] is True
    assert body["items"][0]["done_by"] == "boss"


def test_only_the_reporter_is_notified(client, db, ravi, boss):
    issue = _report(client)
    other = _user(db, "meera")
    _solve(client, boss, issue["id"], reporter=other)
    assert client.get("/issues/mine").json()["unseen_count"] == 0


def test_the_notification_stays_until_seen(client, db, ravi, boss):
    _solve(client, boss, _report(client)["id"], reporter=ravi)
    assert client.get("/issues/mine").json()["unseen_count"] == 1
    assert client.get("/issues/mine").json()["unseen_count"] == 1
    assert client.post("/issues/mine/seen").status_code == 200
    body = client.get("/issues/mine").json()
    assert body["unseen_count"] == 0
    assert body["items"][0]["is_done"] is True


def test_seeing_mine_doesnt_clear_anyone_elses(client, db, ravi, boss):
    issue = _report(client)
    other = _user(db, "meera")
    _sign_in(client, other)
    theirs = _report(client)
    _solve(client, boss, issue["id"])
    _solve(client, boss, theirs["id"], reporter=other)
    client.post("/issues/mine/seen")
    _sign_in(client, ravi)
    assert client.get("/issues/mine").json()["unseen_count"] == 1


def test_reopening_clears_it_and_solving_again_notifies_again(client, db, ravi, boss):
    issue = _report(client)
    _solve(client, boss, issue["id"], reporter=ravi)
    client.post("/issues/mine/seen")

    _sign_in(client, boss)
    reopened = client.patch(f"/issues/{issue['id']}", json={"is_done": False}).json()
    assert (reopened["is_done"], reopened["done_by"], reopened["done_at"]) == (False, None, None)
    assert db.query(AuditLog).filter_by(action="issue.reopen").count() == 1

    _solve(client, boss, issue["id"], reporter=ravi)
    assert client.get("/issues/mine").json()["unseen_count"] == 1


def test_marking_done_twice_changes_nothing(client, db, ravi, boss):
    issue = _report(client)
    _solve(client, boss, issue["id"], reporter=ravi)
    client.post("/issues/mine/seen")
    _solve(client, boss, issue["id"], reporter=ravi)
    assert client.get("/issues/mine").json()["unseen_count"] == 0
    assert db.query(AuditLog).filter_by(action="issue.done").count() == 1


def test_an_unseen_solved_issue_past_the_list_limit_still_counts(client, db, ravi, boss):
    old = _report(client, "Old one")
    for n in range(30):
        db.add(Issue(text=f"Newer {n}", reported_by_id=ravi.id, reported_by="ravi"))
    db.commit()
    _solve(client, boss, old["id"], reporter=ravi)
    body = client.get("/issues/mine").json()
    assert len(body["items"]) == 30
    assert body["unseen_count"] == 1
