import pytest
from passlib.hash import bcrypt

from app.datetime_utils import utcnow
from app.entities import InvoiceItem, ProjectFile, User, UserRole
from app.entities.project import Project
from app.invoices.model import InvoiceCreate, InvoiceItemCreate, InvoiceUpdate
from app.invoices.repository import create_invoice, update_invoice


@pytest.fixture
def logged_in(client, db):
    from app.security import create_access_token

    user = User(username="alan", email="a@example.com", phone="9876543210",
                hashed_password=bcrypt.hash("x" * 12), role=UserRole.ADMIN, is_active=True)
    db.add(user)
    db.commit()
    client.cookies.set("access_token", create_access_token({"sub": "alan", "role": "admin", "tv": 0}))


def _project(db):
    project = Project(project_type="Flex", assigned_to="a", priority="Normal", client_status="Confirmed",
                      start_date=utcnow(), delivery_date=utcnow())
    db.add(project)
    db.commit()
    return project


def _file(db, project, path, name, **kw):
    f = ProjectFile(project_id=project.id, path=path, original_name=name, **kw)
    db.add(f)
    db.commit()
    return f


def _item(description, file_id=None):
    return InvoiceItemCreate(description=description, width=1, height=1, rate=10, pieces=1, unit="ft", project_file_id=file_id)


def _paths(client, invoice):
    return [f["path"] for f in client.get(f"/files/invoice/{invoice.id}").json()]


def test_only_the_files_the_invoice_billed_for_are_listed(client, db, logged_in, tmp_path, monkeypatch):
    monkeypatch.setattr("app.project_files.controller.UPLOAD_DIR", tmp_path)
    project = _project(db)
    billed = _file(db, project, "billed.png", "front.png")
    _file(db, project, "reference.png", "reference.png")  # on the project, never invoiced
    (tmp_path / "billed.png").write_bytes(b"\x89PNG" + b"0" * 50)
    invoice = create_invoice(db, InvoiceCreate(project_id=project.id, items=[_item("Flex – front", billed.id)]), "t")

    files = client.get(f"/files/invoice/{invoice.id}").json()
    assert [f["path"] for f in files] == ["billed.png"]
    assert files[0]["original_available"] and files[0]["is_image"]


def test_a_file_from_another_project_cannot_be_linked(client, db, logged_in):
    mine, other = _project(db), _project(db)
    foreign = _file(db, other, "foreign.png", "foreign.png")
    invoice = create_invoice(db, InvoiceCreate(project_id=mine.id, items=[_item("Flex", foreign.id)]), "t")
    assert db.query(InvoiceItem).filter_by(invoice_id=invoice.id).one().project_file_id is None
    assert _paths(client, invoice) == []


def test_older_invoices_match_files_by_the_generated_line_wording(client, db, logged_in):
    project = _project(db)
    _file(db, project, "a.png", "Shop front.png")
    _file(db, project, "b.png", "Unrelated.png")
    invoice = create_invoice(db, InvoiceCreate(project_id=project.id, items=[_item("Flex – Shop front")]), "t")  # no link
    assert _paths(client, invoice) == ["a.png"]


def test_lines_with_hand_written_wording_match_nothing(client, db, logged_in):
    project = _project(db)
    _file(db, project, "a.png", "Shop front.png")
    invoice = create_invoice(db, InvoiceCreate(project_id=project.id, items=[_item("Custom signage")]), "t")
    assert _paths(client, invoice) == []


def test_editing_an_invoice_keeps_the_link_and_the_same_file_is_listed_once(client, db, logged_in):
    project = _project(db)
    f = _file(db, project, "a.png", "Shop front.png")
    invoice = create_invoice(db, InvoiceCreate(project_id=project.id, items=[_item("Flex – Shop front", f.id)]), "t")
    update_invoice(db, invoice.id, InvoiceUpdate(items=[_item("Flex – Shop front", f.id), _item("Flex – Shop front (copy)", f.id)]), "admin")
    assert _paths(client, invoice) == ["a.png"]


def test_a_deleted_file_drops_out_of_the_gallery(client, db, logged_in):
    project = _project(db)
    f = _file(db, project, "a.png", "Shop front.png")
    invoice = create_invoice(db, InvoiceCreate(project_id=project.id, items=[_item("Custom", f.id)]), "t")
    assert _paths(client, invoice) == ["a.png"]
    db.delete(f)
    db.commit()
    assert _paths(client, invoice) == []


def test_requires_login_and_unknown_invoice_is_404(client, db, logged_in):
    assert client.get("/files/invoice/999").status_code == 404
    client.cookies.clear()
    assert client.get("/files/invoice/1").status_code == 401
