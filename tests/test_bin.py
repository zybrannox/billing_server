"""Deleting moves things to the bin; restoring must put back exactly what was
there, and after 14 days it must really be gone."""
from datetime import timedelta

import pytest
from passlib.hash import bcrypt

from app.bin import service as bin_service
from app.datetime_utils import utcnow
from app.entities import (
    BinItem,
    ClientAccount,
    Company,
    Customer,
    Invoice,
    InvoiceItem,
    InvoicePayment,
    JobRequest,
    ProjectFile,
    Quotation,
    QuotationItem,
    User,
    UserRole,
)
from app.entities.project import Project
from app.invoices.model import InvoiceCreate, InvoiceItemCreate
from app.invoices.repository import create_invoice


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    (tmp_path / "thumbnails").mkdir()
    monkeypatch.setattr(bin_service, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr("app.project_files.controller.UPLOAD_DIR", tmp_path)
    monkeypatch.setattr("app.project_files.service.UPLOAD_DIR", tmp_path)
    monkeypatch.setattr("app.entities.project_file.UPLOAD_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def admin(client, db):
    from app.security import create_access_token

    db.add(User(username="alan", email="alan@example.com", phone="9876543210",
                hashed_password=bcrypt.hash("x" * 12), role=UserRole.ADMIN, is_active=True))
    db.commit()
    client.cookies.set("access_token", create_access_token({"sub": "alan", "role": "admin", "tv": 0}))
    client.headers["X-Requested-With"] = "XMLHttpRequest"


def _customer(db, name="Asha", company=None, email=None):
    c = Customer(first_name=name, last_name="K", contact_number="9876543211", email=email,
                 company_id=company.id if company else None)
    db.add(c)
    db.commit()
    return c


def _project(db, customer=None, **kw):
    now = utcnow()
    p = Project(project_type="Flex", assigned_to="alan", priority="Normal", client_status="Confirmed",
                print_status="In Progress", start_date=now, delivery_date=now,
                customer_id=customer.id if customer else None, **kw)
    db.add(p)
    db.commit()
    return p


def _file(db, uploads, project, path="art.png", content=b"artwork"):
    (uploads / path).write_bytes(content)
    (uploads / "thumbnails" / path).write_bytes(b"thumb")
    f = ProjectFile(project_id=project.id, path=path, original_name="Front banner.png", pixel_width=800)
    db.add(f)
    db.commit()
    return f


def _bin(client, **params):
    res = client.get("/bin/", params=params)
    assert res.status_code == 200, res.text
    return res.json()


def _only(client):
    items = _bin(client)["items"]
    assert len(items) == 1
    return items[0]


# --- projects and their files ---------------------------------------------------


def test_a_deleted_project_leaves_every_list_and_keeps_its_files_safe(client, db, admin, uploads):
    project = _project(db, _customer(db))
    _file(db, uploads, project)
    pid = project.id

    assert client.delete(f"/projects/{pid}").status_code == 200

    assert client.get(f"/projects/{pid}").status_code == 404
    assert client.get("/projects/").json()["total"] == 0
    assert db.query(ProjectFile).count() == 0
    assert not (uploads / "art.png").exists()

    item = _only(client)
    assert item["item_type"] == "project"
    assert item["label"] == "Flex – Asha K"
    assert item["detail"] == "1 file"
    assert item["size_bytes"] == len(b"artwork")
    assert item["deleted_by"] == "alan"


def test_restoring_a_project_brings_back_the_same_records_and_files(client, db, admin, uploads):
    project = _project(db, _customer(db), description="Shop front", pinned=True)
    f = _file(db, uploads, project)
    pid, fid, start = project.id, f.id, project.start_date

    client.delete(f"/projects/{pid}")
    res = client.post(f"/bin/{_only(client)['id']}/restore")
    assert res.status_code == 200, res.text

    db.expire_all()
    back = db.get(Project, pid)
    assert back.description == "Shop front"
    assert back.pinned is True
    assert back.start_date == start
    assert back.files[0].id == fid
    assert back.files[0].original_name == "Front banner.png"
    assert back.files[0].pixel_width == 800
    assert (uploads / "art.png").read_bytes() == b"artwork"
    assert (uploads / "thumbnails" / "art.png").read_bytes() == b"thumb"
    assert _bin(client)["total"] == 0
    assert not (uploads / ".bin").exists() or not list((uploads / ".bin").iterdir())


def test_an_invoiced_project_still_cannot_be_deleted(client, db, admin, uploads):
    project = _project(db, _customer(db))
    _file(db, uploads, project)
    create_invoice(db, InvoiceCreate(project_id=project.id, items=[
        InvoiceItemCreate(description="x", width=1, height=1, rate=10, pieces=1, unit="ft")]), "t")

    res = client.delete(f"/projects/{project.id}")
    assert res.status_code == 400
    assert "invoiced" in res.json()["detail"]
    assert db.get(Project, project.id) is not None
    assert (uploads / "art.png").exists()
    assert _bin(client)["total"] == 0


def test_bulk_delete_is_all_or_nothing(client, db, admin, uploads):
    free, invoiced = _project(db), _project(db)
    _file(db, uploads, free)
    create_invoice(db, InvoiceCreate(project_id=invoiced.id, items=[
        InvoiceItemCreate(description="x", width=1, height=1, rate=10, pieces=1, unit="ft")]), "t")

    assert client.post("/projects/bulk-delete", json={"ids": [free.id, invoiced.id]}).status_code == 400
    db.expire_all()
    assert db.get(Project, free.id) is not None
    assert (uploads / "art.png").exists()
    assert _bin(client)["total"] == 0

    assert client.post("/projects/bulk-delete", json={"ids": [free.id]}).status_code == 200
    assert _bin(client)["total"] == 1


def test_a_single_file_can_be_binned_and_restored(client, db, admin, uploads):
    project = _project(db)
    keep = _file(db, uploads, project, "keep.png")
    drop = _file(db, uploads, project, "drop.png")
    drop_id = drop.id

    assert client.delete("/files/drop.png").status_code == 200
    db.expire_all()
    assert [f.path for f in db.get(Project, project.id).files] == [keep.path]
    assert not (uploads / "drop.png").exists()
    item = _only(client)
    assert (item["item_type"], item["label"]) == ("file", "Front banner.png")

    assert client.post(f"/bin/{item['id']}/restore").status_code == 200
    db.expire_all()
    assert db.get(ProjectFile, drop_id).project_id == project.id
    assert (uploads / "drop.png").exists()


def test_a_binned_file_cant_be_restored_without_its_project(client, db, admin, uploads):
    project = _project(db)
    _file(db, uploads, project, "a.png")
    client.delete("/files/a.png")
    file_item = _only(client)
    client.delete(f"/projects/{project.id}")

    res = client.post(f"/bin/{file_item['id']}/restore")
    assert res.status_code == 409
    assert "Restore the project" in res.json()["detail"]
    assert (uploads / ".bin" / str(file_item["id"]) / "a.png").exists()


def test_an_upload_not_yet_on_a_project_is_just_cleaned_up(client, db, admin, uploads):
    (uploads / "picked.png").write_bytes(b"x")
    assert client.delete("/files/picked.png").status_code == 200
    assert not (uploads / "picked.png").exists()
    assert _bin(client)["total"] == 0


def test_bulk_file_delete_bins_the_linked_and_cleans_the_rest(client, db, admin, uploads):
    project = _project(db)
    _file(db, uploads, project, "linked.png")
    (uploads / "loose.png").write_bytes(b"x")
    res = client.post("/files/bulk-delete", json={"paths": ["linked.png", "loose.png", "gone.png"]})
    assert res.status_code == 200
    assert _only(client)["label"] == "Front banner.png"
    assert not (uploads / "loose.png").exists()


def test_deleting_a_file_clears_and_restores_its_invoice_link(client, db, admin, uploads):
    project = _project(db)
    f = _file(db, uploads, project)
    invoice = create_invoice(db, InvoiceCreate(project_id=project.id, items=[
        InvoiceItemCreate(description="x", width=1, height=1, rate=10, pieces=1, unit="ft", project_file_id=f.id)]), "t")
    item_id, file_id = invoice.items[0].id, f.id

    client.delete("/files/art.png")
    db.expire_all()
    assert db.get(InvoiceItem, item_id).project_file_id is None

    client.post(f"/bin/{_only(client)['id']}/restore")
    db.expire_all()
    assert db.get(InvoiceItem, item_id).project_file_id == file_id


# --- invoices, with their money --------------------------------------------------


def test_restoring_an_invoice_keeps_its_lines_and_payments_exact(client, db, admin, uploads):
    project = _project(db, _customer(db))
    invoice = create_invoice(db, InvoiceCreate(project_id=project.id, items=[
        InvoiceItemCreate(description="Banner", width=8, height=4, rate=12.5, pieces=2, unit="ft")]), "t")
    db.add(InvoicePayment(invoice_id=invoice.id, amount=100, payment_method="UPI", recorded_by="alan"))
    db.commit()
    iid, number, total = invoice.id, invoice.invoice_number, invoice.amount

    assert client.delete(f"/invoices/{iid}").status_code == 200
    db.expire_all()
    assert db.get(Invoice, iid) is None
    assert db.query(InvoiceItem).count() == 0
    assert db.query(InvoicePayment).count() == 0
    item = _only(client)
    assert (item["label"], item["detail"]) == (number, "Asha K")

    assert client.post(f"/bin/{item['id']}/restore").status_code == 200
    db.expire_all()
    back = db.get(Invoice, iid)
    assert back.invoice_number == number
    assert back.amount == total
    assert back.items[0].description == "Banner"
    assert db.query(InvoicePayment).one().amount == 100


def test_restoring_a_quotation_keeps_its_lines(client, db, admin, uploads):
    customer = _customer(db)
    q = Quotation(quotation_number="QUOTE-1", customer_id=customer.id, project_type="Flex", subtotal=50,
                  amount=50, valid_until=utcnow())
    q.items = [QuotationItem(description="Line", width=1, height=1, rate=50, pieces=1, unit="ft", sq_ft=1, total=50)]
    db.add(q)
    db.commit()
    qid = q.id

    assert client.delete(f"/quotations/{qid}").status_code == 200
    db.expire_all()
    assert db.get(Quotation, qid) is None
    assert db.query(QuotationItem).count() == 0

    assert client.post(f"/bin/{_only(client)['id']}/restore").status_code == 200
    db.expire_all()
    assert db.get(Quotation, qid).items[0].description == "Line"


def test_a_quotation_cant_be_restored_without_its_customer(client, db, admin, uploads):
    customer = _customer(db)
    q = Quotation(quotation_number="QUOTE-1", customer_id=customer.id, project_type="Flex", subtotal=50,
                  amount=50, valid_until=utcnow())
    db.add(q)
    db.commit()
    client.delete(f"/quotations/{q.id}")
    item = _only(client)
    assert client.delete(f"/customers/{customer.id}").status_code == 200

    res = client.post(f"/bin/{item['id']}/restore")
    assert res.status_code == 409
    assert "Restore the customer" in res.json()["detail"]


# --- customers, companies, employees ---------------------------------------------


def test_a_customer_with_a_project_still_cannot_be_deleted(client, db, admin, uploads):
    customer = _customer(db)
    _project(db, customer)
    res = client.delete(f"/customers/{customer.id}")
    assert res.status_code == 400
    assert "projects or invoices" in res.json()["detail"]
    assert _bin(client)["total"] == 0


def test_a_customer_comes_back_with_their_portal_login_and_job_requests(client, db, admin, uploads):
    customer = _customer(db, email="asha@example.com")
    account = ClientAccount(customer_id=customer.id, email="asha@example.com", is_active=True)
    db.add(account)
    db.add(JobRequest(customer_id=customer.id, description="Please print", status="pending"))
    db.commit()
    cid = customer.id

    assert client.delete(f"/customers/{cid}").status_code == 200
    db.expire_all()
    assert db.query(ClientAccount).count() == 0
    assert db.query(JobRequest).count() == 0

    assert client.post(f"/bin/{_only(client)['id']}/restore").status_code == 200
    db.expire_all()
    assert db.get(Customer, cid).email == "asha@example.com"
    assert db.query(ClientAccount).one().customer_id == cid
    assert db.query(JobRequest).one().description == "Please print"


def test_a_company_gets_its_contacts_back_unless_they_have_moved_on(client, db, admin, uploads):
    company, other = Company(name="Acme"), Company(name="Other")
    db.add_all([company, other])
    db.commit()
    stayed, moved = _customer(db, "Stayed", company), _customer(db, "Moved", company)
    cid = company.id

    assert client.delete(f"/companies/{cid}").status_code == 200
    db.expire_all()
    assert db.get(Customer, stayed.id).company_id is None

    db.get(Customer, moved.id).company_id = other.id
    db.commit()

    assert client.post(f"/bin/{_only(client)['id']}/restore").status_code == 200
    db.expire_all()
    assert db.get(Customer, stayed.id).company_id == cid
    assert db.get(Customer, moved.id).company_id == other.id


def test_an_employee_comes_back_with_the_same_role_and_password(client, db, admin, uploads):
    hashed = bcrypt.hash("y" * 12)
    user = User(username="ravi", email="ravi@example.com", phone="9876543212", hashed_password=hashed,
                role=UserRole.MODERATOR, is_active=True)
    db.add(user)
    db.commit()
    uid = user.id

    assert client.delete(f"/users/{uid}").status_code == 200
    db.expire_all()
    assert db.get(User, uid) is None
    assert (_only(client)["item_type"], _only(client)["label"]) == ("employee", "ravi")

    assert client.post(f"/bin/{_only(client)['id']}/restore").status_code == 200
    db.expire_all()
    back = db.get(User, uid)
    assert back.role == UserRole.MODERATOR
    assert back.hashed_password == hashed


def test_restoring_explains_when_the_details_are_now_taken(client, db, admin, uploads):
    user = User(username="ravi", email="ravi@example.com", phone="9876543212",
                hashed_password=bcrypt.hash("y" * 12), role=UserRole.USER, is_active=True)
    db.add(user)
    db.commit()
    client.delete(f"/users/{user.id}")
    item = _only(client)
    db.add(User(username="ravi", email="new@example.com", phone="9876543213",
                hashed_password=bcrypt.hash("y" * 12), role=UserRole.USER, is_active=True))
    db.commit()

    res = client.post(f"/bin/{item['id']}/restore")
    assert res.status_code == 409
    assert "same details" in res.json()["detail"]
    assert _bin(client)["total"] == 1  # still there to try again


# --- 14 days ---------------------------------------------------------------------


def test_items_are_kept_for_14_days(client, db, admin, uploads):
    project = _project(db)
    client.delete(f"/projects/{project.id}")
    item = db.query(BinItem).one()
    assert item.expires_at - item.deleted_at == timedelta(days=14)
    assert _bin(client)["retention_days"] == 14


def test_expired_items_are_erased_with_their_files_and_nothing_else(client, db, admin, uploads):
    old, recent = _project(db), _project(db)
    _file(db, uploads, old, "old.png")
    _file(db, uploads, recent, "recent.png")
    client.delete(f"/projects/{old.id}")
    client.delete(f"/projects/{recent.id}")
    old_item, recent_item = db.query(BinItem).order_by(BinItem.id).all()
    old_id, recent_id = old_item.id, recent_item.id
    old_item.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()

    assert bin_service.erase_expired(db) == 1
    db.expire_all()
    assert db.get(BinItem, old_id) is None
    assert not (uploads / ".bin" / str(old_id)).exists()
    assert db.get(BinItem, recent_id) is not None
    assert (uploads / ".bin" / str(recent_id) / "recent.png").exists()


def test_an_expired_item_is_never_offered_even_if_the_job_didnt_run(client, db, admin, uploads):
    client.delete(f"/projects/{_project(db).id}")
    db.query(BinItem).one().expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert _bin(client)["total"] == 0


# --- managing the bin ------------------------------------------------------------


def test_delete_forever_and_empty(client, db, admin, uploads):
    first, second = _project(db), _project(db)
    _file(db, uploads, first, "a.png")
    _file(db, uploads, second, "b.png")
    client.delete(f"/projects/{first.id}")
    client.delete(f"/projects/{second.id}")

    target = _bin(client)["items"][1]["id"]
    assert client.delete(f"/bin/{target}").status_code == 200
    assert _bin(client)["total"] == 1
    assert not (uploads / ".bin" / str(target)).exists()

    assert client.delete("/bin/").json()["count"] == 1
    assert _bin(client)["total"] == 0
    assert list((uploads / ".bin").iterdir()) == []


def test_filter_counts_and_paging(client, db, admin, uploads):
    for _ in range(3):
        client.delete(f"/projects/{_project(db).id}")
    client.delete(f"/companies/{_company(db).id}")

    body = _bin(client, item_type="company")
    assert body["total"] == 1
    assert {c["item_type"]: c["count"] for c in body["counts"]} == {"project": 3, "company": 1}
    assert len(_bin(client, page=1, page_size=2)["items"]) == 2
    assert _bin(client)["items"][0]["item_type"] == "company"  # newest first


def _company(db):
    company = Company(name="Acme")
    db.add(company)
    db.commit()
    return company


def test_snapshots_arent_sent_to_the_browser(client, db, admin, uploads):
    client.delete(f"/projects/{_project(db).id}")
    assert "snapshot" not in _only(client)


def test_the_bin_is_admin_only(client, db, uploads):
    from app.security import create_access_token

    db.add(User(username="emp", email="e@example.com", phone="9876543214",
                hashed_password=bcrypt.hash("x" * 12), role=UserRole.USER, is_active=True))
    db.commit()
    client.cookies.set("access_token", create_access_token({"sub": "emp", "role": "user", "tv": 0}))
    client.headers["X-Requested-With"] = "XMLHttpRequest"
    assert client.get("/bin/").status_code == 403
    assert client.post("/bin/1/restore").status_code == 403
    assert client.delete("/bin/1").status_code == 403
    assert client.delete("/bin/").status_code == 403


def test_restores_and_erasures_are_audited(client, db, admin, uploads):
    client.delete(f"/projects/{_project(db).id}")
    client.post(f"/bin/{_only(client)['id']}/restore")
    client.delete(f"/projects/{db.query(Project).one().id}")
    client.delete(f"/bin/{_only(client)['id']}")
    actions = [r["action"] for r in client.get("/audit-log/").json()["items"]]
    assert actions[:2] == ["bin.erase", "project.delete"]
    assert "bin.restore" in actions
