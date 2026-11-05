"""Nobody reaches data that isn't theirs, secrets never leave the server, and
nothing is destroyed without a way back."""
import re
from datetime import timedelta

import pytest
from passlib.hash import bcrypt

from app.datetime_utils import utcnow
from app.entities import ClientAccount, Customer, JobRequest, JobRequestFile, User, UserRole
from app.entities.project import Project
from app.entities.project_file import ProjectFile
from app.invoices.model import InvoiceCreate, InvoiceItemCreate
from app.invoices.repository import create_invoice
from app.main import app
from app.project_files import retention
from app.project_files import service as file_service
from app.security import create_access_token, create_client_access_token

LINE = {"description": "Banner", "width": 1, "height": 1, "rate": 100, "pieces": 1, "unit": "ft"}

# What a signed-in portal client may reach. Everything else must refuse them.
CLIENT_ROUTES = re.compile(r"^/(portal|client-auth|public)/|^/auth/(login|logout|forgot-password|reset-password)$|^/job-requests/(upload|mine)|^/job-requests/$|^/job-requests/\{job_request_id\}/attach-files$|^/document-settings/(logo)?$|^/$")


def _operations():
    for path, methods in app.openapi()["paths"].items():
        for method in methods:
            yield method, path


def _staff(client, db, name="ravi", role=UserRole.USER, permissions=()):
    user = User(username=name, email=f"{name}@example.com", phone="9" + str(abs(hash(name)))[:9].zfill(9),
                hashed_password=bcrypt.hash("x" * 12), role=role, is_active=True, permissions=list(permissions))
    db.add(user)
    db.commit()
    client.cookies.set("access_token", create_access_token({"sub": name, "role": role.value, "tv": 0}))
    client.headers["X-Requested-With"] = "XMLHttpRequest"
    return user


def _customer(db, first="Asha", phone="9876500001"):
    customer = Customer(first_name=first, last_name="Rao", contact_number=phone)
    db.add(customer)
    db.commit()
    return customer


def _as_client(client, db, customer):
    account = ClientAccount(customer_id=customer.id, email=f"{customer.first_name}@example.com",
                            hashed_password=bcrypt.hash("x" * 12), is_active=True, activated_at=utcnow())
    db.add(account)
    db.commit()
    client.cookies.clear()
    client.cookies.set("client_access_token", create_client_access_token({"sub": str(account.id), "tv": 0}))
    client.headers["X-Requested-With"] = "XMLHttpRequest"
    return account


def _project(db, customer=None, **fields):
    now = utcnow()
    project = Project(project_type="Flex", customer_id=customer.id if customer else None, assigned_to="t", priority="Normal",
                      client_status="Confirmed", print_status=fields.pop("print_status", "In Progress"),
                      start_date=now, delivery_date=now, **fields)
    db.add(project)
    db.commit()
    return project


def _invoice(db, project):
    return create_invoice(db, InvoiceCreate(project_id=project.id, items=[InvoiceItemCreate(**LINE)]), "t")


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(file_service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr("app.job_requests.service.UPLOAD_DIR", tmp_path)
    return tmp_path


# --- who can reach what ------------------------------------------------------


def test_a_portal_client_is_refused_by_every_staff_route(client, db):
    _as_client(client, db, _customer(db))
    reachable = []
    for method, path in _operations():
        if CLIENT_ROUTES.search(path):
            continue
        status = client.request(method.upper(), re.sub(r"\{[^}]+\}", "1", path), json={}).status_code
        if status not in (401, 403):
            reachable.append((method, path, status))
    assert reachable == []


@pytest.mark.parametrize("method,path", [
    ("get", "/users/"),
    ("get", "/users/1"),
    ("get", "/users/1/profile"),
    ("put", "/users/1/permissions"),
    ("get", "/audit-log/"),
    ("get", "/bin/"),
    ("post", "/bin/1/restore"),
    ("get", "/system-health"),
    ("get", "/invoices/"),
    ("get", "/invoices/summary"),
    ("delete", "/invoices/1"),
    ("delete", "/customers/1"),
    ("put", "/customers/1"),
    ("delete", "/companies/1"),
    ("post", "/projects/bulk-delete"),
    ("get", "/job-requests/"),
    ("get", "/job-requests/1"),
    ("post", "/job-requests/1/convert"),
    ("post", "/job-requests/1/reject"),
    ("post", "/files/purge-stale"),
])
def test_an_employee_without_access_is_refused(client, db, method, path):
    _staff(client, db)
    assert client.request(method.upper(), path, json={}).status_code == 403


def test_a_client_only_sees_their_own_orders_and_invoices(client, db):
    mine, other = _customer(db), _customer(db, "Vikram", "9876500002")
    my_project, other_project = _project(db, mine), _project(db, other)
    my_invoice, other_invoice = _invoice(db, my_project), _invoice(db, other_project)
    _as_client(client, db, mine)

    assert [o["id"] for o in client.get("/portal/orders").json()["items"]] == [my_project.id]
    assert [i["id"] for i in client.get("/portal/invoices").json()["items"]] == [my_invoice.id]
    assert client.get(f"/portal/orders/{my_project.id}").status_code == 200
    assert client.get(f"/portal/invoices/{my_invoice.id}").status_code == 200
    assert client.get(f"/portal/orders/{other_project.id}").status_code == 404
    assert client.get(f"/portal/invoices/{other_invoice.id}").status_code == 404


def test_a_client_only_sees_their_own_job_requests(client, db):
    mine, other = _customer(db), _customer(db, "Vikram", "9876500002")
    theirs = JobRequest(customer_id=other.id, description="Private job")
    db.add(theirs)
    db.commit()
    _as_client(client, db, mine)
    assert client.get("/job-requests/mine").json()["items"] == []
    assert client.get(f"/job-requests/mine/{theirs.id}").status_code == 404
    assert client.post(f"/job-requests/{theirs.id}/attach-files", json={"files": []}).status_code == 404


def test_a_staff_token_is_not_a_client_token_or_the_reverse(client, db):
    _staff(client, db)
    assert client.get("/portal/orders").status_code == 401
    _as_client(client, db, _customer(db))
    assert client.get("/projects/").status_code == 401


# --- clients can't touch files that aren't theirs ------------------------------


def _attached_file(db, uploads, name="artwork-uuid.png"):
    (uploads / name).write_bytes(b"artwork")
    project = _project(db)
    db.add(ProjectFile(project_id=project.id, path=name, original_name="artwork.png"))
    db.commit()
    return name


def test_a_client_cannot_delete_a_file_already_on_a_project(client, db, uploads):
    name = _attached_file(db, uploads)
    _as_client(client, db, _customer(db))
    assert client.delete(f"/job-requests/upload/{name}").status_code == 404
    assert (uploads / name).exists()


def test_a_client_cannot_delete_a_file_on_a_job_request(client, db, uploads):
    customer = _customer(db)
    job = JobRequest(customer_id=customer.id, description="Job")
    db.add(job)
    db.commit()
    (uploads / "attached.png").write_bytes(b"x")
    db.add(JobRequestFile(job_request_id=job.id, path="attached.png", original_name="a.png"))
    db.commit()
    _as_client(client, db, _customer(db, "Vikram", "9876500002"))
    assert client.delete("/job-requests/upload/attached.png").status_code == 404
    assert (uploads / "attached.png").exists()


def test_a_client_can_still_remove_their_own_unattached_upload(client, db, uploads, monkeypatch):
    monkeypatch.setattr("app.job_requests.controller.delete_uploaded_file", lambda name: (uploads / name).unlink() or True)
    (uploads / "fresh.png").write_bytes(b"x")
    _as_client(client, db, _customer(db))
    assert client.delete("/job-requests/upload/fresh.png").status_code == 200
    assert not (uploads / "fresh.png").exists()


@pytest.mark.parametrize("path", ["artwork-uuid.png", "../secrets.txt", "missing.png"])
def test_a_client_cannot_attach_a_file_that_isnt_theirs_to_give(client, db, uploads, path):
    _attached_file(db, uploads)
    customer = _customer(db)
    job = JobRequest(customer_id=customer.id, description="Job")
    db.add(job)
    db.commit()
    _as_client(client, db, customer)
    res = client.post(f"/job-requests/{job.id}/attach-files", json={"files": [{"path": path, "original_name": "x.png"}]})
    assert res.status_code == 400
    assert db.query(JobRequestFile).count() == 0


def test_a_client_can_attach_their_own_upload(client, db, uploads):
    (uploads / "fresh.png").write_bytes(b"x")
    customer = _customer(db)
    job = JobRequest(customer_id=customer.id, description="Job")
    db.add(job)
    db.commit()
    _as_client(client, db, customer)
    res = client.post(f"/job-requests/{job.id}/attach-files", json={"files": [{"path": "fresh.png", "original_name": "x.png"}]})
    assert res.status_code == 200
    assert db.query(JobRequestFile).count() == 1


@pytest.mark.parametrize("route", ["/files/download/", "/files/view/", "/files/thumbnail/"])
@pytest.mark.parametrize("name", ["..%2f.env", "%2e%2e%2f.env", "..%2f..%2fetc%2fpasswd"])
def test_file_routes_cannot_climb_out_of_uploads(client, db, route, name):
    _staff(client, db)
    res = client.get(route + name)
    assert res.status_code in (400, 404)
    assert b"SECRET_KEY" not in res.content and b"root:" not in res.content


# --- secrets stay on the server --------------------------------------------------


def test_no_response_ever_contains_password_hashes_or_reset_codes(client, db):
    admin = _staff(client, db, "boss", UserRole.ADMIN)
    employee = User(username="ravi", email="ravi@example.com", phone="9000000022", hashed_password=bcrypt.hash("x" * 12),
                    role=UserRole.USER, is_active=True, reset_code="123456")
    db.add(employee)
    db.commit()
    client.put(f"/users/{employee.id}", json={"email": "ravi2@example.com"})
    client.patch(f"/users/{employee.id}/password", json={"new_password": "Another-Str0ng-Pass!", "password": "Another-Str0ng-Pass!"})
    client.delete(f"/users/{employee.id}")

    for url in ["/users/", f"/users/{admin.id}", f"/users/{admin.id}/profile", "/audit-log/", "/bin/", "/auth/me"]:
        res = client.get(url)
        assert res.status_code == 200, url
        body = res.text
        assert "$2b$" not in body, url
        assert "123456" not in body, url
        # The activity log may say a password changed, but never to what.
        for entry in res.json().get("items", []) if url == "/audit-log/" else []:
            for change in entry["detail"].get("changes", []) if entry.get("detail") else []:
                if "password" in change["field"]:
                    assert not str(change.get("from") or "").startswith("$") and not str(change.get("to") or "").startswith("$")


# --- files aren't destroyed too early -------------------------------------------


@pytest.fixture
def retained(tmp_path, monkeypatch):
    thumbnails = tmp_path / "thumbs"
    thumbnails.mkdir()
    monkeypatch.setattr(retention, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(retention, "THUMBNAIL_DIR", thumbnails)
    monkeypatch.setattr(retention, "generate_thumbnail", lambda name: None)

    def add(db, project, name="art.png", age_days=30, thumbnail=True):
        (tmp_path / name).write_bytes(b"original")
        if thumbnail:
            (thumbnails / name).write_bytes(b"thumb")
        db.add(ProjectFile(project_id=project.id, path=name, original_name=name, created_at=utcnow() - timedelta(days=age_days)))
        db.commit()
        return tmp_path / name

    return add


def test_an_invoiced_job_still_being_printed_keeps_its_artwork(db, retained):
    project = _project(db)
    _invoice(db, project)
    original = retained(db, project)
    retention.purge_stale_originals(db)
    assert original.exists()


def test_a_job_finished_today_keeps_old_artwork_for_the_full_period(db, retained):
    project = _project(db, print_status="Completed", print_completed_at=utcnow())
    original = retained(db, project)
    retention.purge_stale_originals(db)
    assert original.exists()


def test_a_job_delivered_today_keeps_old_artwork_for_the_full_period(db, retained):
    project = _project(db, delivered_at=utcnow())
    original = retained(db, project)
    retention.purge_stale_originals(db)
    assert original.exists()


def test_artwork_goes_only_after_the_job_has_been_done_a_while(db, retained):
    project = _project(db, print_status="Completed", print_completed_at=utcnow() - timedelta(days=8))
    original = retained(db, project)
    assert retention.purge_stale_originals(db)["purged"] == 1
    assert not original.exists()


def test_a_file_with_nothing_to_show_for_it_is_never_removed(db, retained):
    project = _project(db, print_status="Completed", print_completed_at=utcnow() - timedelta(days=8))
    original = retained(db, project, "design.pdf", thumbnail=False)
    assert retention.purge_stale_originals(db)["purged"] == 0
    assert original.exists()


def test_employees_cannot_bulk_delete_projects_but_admins_can(client, db):
    project = _project(db)
    _staff(client, db)
    assert client.post("/projects/bulk-delete", json={"ids": [project.id]}).status_code == 403
    assert db.query(Project).count() == 1
    _staff(client, db, "boss", UserRole.ADMIN)
    assert client.post("/projects/bulk-delete", json={"ids": [project.id]}).status_code == 200
    assert db.query(Project).count() == 0
    assert client.get("/bin/").json()["total"] == 1
