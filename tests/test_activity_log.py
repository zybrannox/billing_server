"""All activity must show what changed, from what to what, and who did it."""
from datetime import timedelta

import pytest
from passlib.hash import bcrypt

from app.bin import service as bin_service
from app.datetime_utils import utcnow
from app.entities import AuditLog, BinItem, Company, Customer, ListOption, ProjectFile, User, UserRole
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

    db.add(User(username="asha", email="asha@example.com", phone="9876543210",
                hashed_password=bcrypt.hash("x" * 12), role=UserRole.ADMIN, is_active=True))
    db.commit()
    client.cookies.set("access_token", create_access_token({"sub": "asha", "role": "admin", "tv": 0}))
    client.headers["X-Requested-With"] = "XMLHttpRequest"


def _project(db, **kw):
    now = utcnow()
    values = dict(project_type="Flex", assigned_to="asha", priority="Normal", client_status="Confirmed",
                  print_status="In Progress", start_date=now, delivery_date=now)
    values.update(kw)
    p = Project(**values)
    db.add(p)
    db.commit()
    return p


def _clear_log(db):
    db.query(AuditLog).delete()
    db.commit()


def _log(client, **params):
    res = client.get("/audit-log/", params=params)
    assert res.status_code == 200, res.text
    return res.json()["items"]


def _changes(entry):
    return {c["field"]: (c.get("from"), c.get("to")) for c in entry["detail"]["changes"]}


# --- modifications --------------------------------------------------------------


def test_an_edit_shows_before_after_and_who(client, db, admin):
    project = _project(db, description="Old words", print_status="Pending")
    _clear_log(db)

    res = client.put(f"/projects/{project.id}", json={"description": "New words", "print_status": "In Progress"})
    assert res.status_code == 200

    entry = _log(client)[0]
    assert entry["action"] == "project.update"
    assert entry["actor"] == "asha"
    assert entry["entity_id"] == project.id
    assert entry["detail"]["label"] == "Flex"
    assert _changes(entry) == {
        "description": ("Old words", "New words"),
        "print_status": ("Pending", "In Progress"),
    }
    assert {c["label"] for c in entry["detail"]["changes"]} == {"Description", "Print status"}


def test_saving_without_changing_anything_logs_nothing(client, db, admin):
    project = _project(db, description="Same")
    _clear_log(db)
    assert client.put(f"/projects/{project.id}", json={"description": "Same", "client_status": "Confirmed"}).status_code == 200
    assert _log(client) == []


def test_only_what_actually_changed_is_listed(client, db, admin):
    project = _project(db, description="Same")
    _clear_log(db)
    client.put(f"/projects/{project.id}", json={"description": "Same", "client_status": "Correction"})
    assert _changes(_log(client)[0]) == {"client_status": ("Confirmed", "Correction")}


def test_a_customer_shows_a_name_not_an_id(client, db, admin):
    first = Customer(first_name="Ravi", last_name="K", contact_number="9876543211")
    second = Customer(first_name="Meera", last_name="S", contact_number="9876543212")
    db.add_all([first, second])
    db.commit()
    project = _project(db, customer_id=first.id)
    _clear_log(db)

    client.put(f"/projects/{project.id}", json={"customer_id": second.id})
    entry = _log(client)[0]
    assert _changes(entry) == {"customer_id": ("Ravi K", "Meera S")}
    assert entry["detail"]["label"] == "Flex – Meera S"


def test_the_true_before_value_is_recorded_after_a_previous_save(db):
    """After a commit a row forgets its values; "before" must not come out blank."""
    project = _project(db, description="Original")
    db.query(AuditLog).delete()
    db.commit()  # expires the project's attributes
    project.description = "Changed"
    db.commit()
    entry = db.query(AuditLog).one()
    assert entry.detail["changes"][0]["from"] == "Original"
    assert entry.detail["changes"][0]["to"] == "Changed"


def test_two_saves_in_one_go_show_the_overall_change(db):
    project = _project(db, description="A")
    db.query(AuditLog).delete()
    db.commit()
    project.description = "B"
    db.flush()
    project.description = "C"
    db.commit()
    entry = db.query(AuditLog).one()
    assert (entry.detail["changes"][0]["from"], entry.detail["changes"][0]["to"]) == ("A", "C")


def test_a_rolled_back_change_leaves_no_entry(db):
    project = _project(db, description="A")
    db.query(AuditLog).delete()
    db.commit()
    project.description = "B"
    db.flush()
    db.rollback()
    db.commit()
    assert db.query(AuditLog).count() == 0


def test_a_date_sent_back_as_text_isnt_a_change():
    from app.audit.tracker import _plain
    from app.entities.project import Project as P

    column = P.__table__.c.delivery_date
    when = utcnow().replace(microsecond=0)
    assert _plain(column, when) == _plain(column, when.isoformat() + "+00:00")
    assert _plain(column, when) == _plain(column, when.isoformat() + "Z")


def test_hidden_priority_isnt_shown(db):
    project = _project(db, priority="Normal")
    db.query(AuditLog).delete()
    db.commit()
    project.priority = "Urgent"
    db.commit()
    assert db.query(AuditLog).count() == 0


# --- everything else people change ----------------------------------------------


def test_creating_records_says_what_was_created(client, db, admin):
    res = client.post("/customers", json={"first_name": "Ravi", "last_name": "K", "contact_number": "9876543211"})
    assert res.status_code in (200, 201), res.text
    entry = _log(client, entity_type="customer")[0]
    assert (entry["action"], entry["actor"], entry["detail"]["label"]) == ("customer.create", "asha", "Ravi K")
    assert _changes(entry)["contact_number"] == (None, "9876543211")


def test_company_employee_and_dropdown_edits_are_logged(client, db, admin):
    company = Company(name="Acme")
    option = ListOption(category="item_type", value="Flex", rate=10)
    employee = User(username="ravi", email="ravi@example.com", phone="9876543212",
                    hashed_password=bcrypt.hash("y" * 12), role=UserRole.USER, is_active=True)
    db.add_all([company, option, employee])
    db.commit()
    _clear_log(db)

    assert client.put(f"/companies/{company.id}", json={"name": "Acme Ltd"}).status_code == 200
    assert client.patch(f"/list-options/{option.id}/deactivate").status_code == 200
    assert client.put(f"/users/{employee.id}", json={"is_active": False}).status_code == 200

    by_action = {e["action"]: e for e in _log(client)}
    assert _changes(by_action["company.update"]) == {"name": ("Acme", "Acme Ltd")}
    assert _changes(by_action["list_option.update"]) == {"is_active": (True, False)}
    assert _changes(by_action["user.update"]) == {"is_active": (True, False)}
    assert all(e["actor"] == "asha" for e in by_action.values())


def test_passwords_are_logged_without_their_values(db):
    user = User(username="ravi", email="ravi@example.com", phone="9876543212",
                hashed_password="old-hash", role=UserRole.USER, is_active=True)
    db.add(user)
    db.commit()
    db.query(AuditLog).delete()
    db.commit()

    user.hashed_password = "new-hash"
    db.commit()

    entry = db.query(AuditLog).one()
    assert entry.actor == "ravi"  # nobody signed in: reset their own password
    assert entry.detail["changes"] == [{"field": "hashed_password", "label": "Password", "hidden": True}]
    assert "hash" not in str(entry.detail).replace("hashed_password", "")


def test_a_new_users_password_isnt_stored_either(db):
    db.add(User(username="ravi", email="ravi@example.com", phone="9876543212",
                hashed_password="secret-hash", role=UserRole.USER, is_active=True))
    db.commit()
    assert "secret-hash" not in str(db.query(AuditLog).filter_by(action="user.create").one().detail)


def test_a_failed_sign_in_doesnt_read_as_an_edit(db):
    user = User(username="ravi", email="ravi@example.com", phone="9876543212",
                hashed_password="h", role=UserRole.USER, is_active=True)
    db.add(user)
    db.commit()
    db.query(AuditLog).delete()
    db.commit()
    user.failed_login_count = 1
    db.commit()
    assert db.query(AuditLog).count() == 0


# --- invoices -------------------------------------------------------------------


def _line(description="Banner", rate=10):
    return InvoiceItemCreate(description=description, width=8, height=4, rate=rate, pieces=2, unit="ft")


def test_a_new_invoice_has_its_final_number_and_its_lines(client, db, admin):
    project = _project(db)
    _clear_log(db)
    res = client.post("/invoices/", json={"project_id": project.id, "items": [_line().model_dump()]})
    assert res.status_code == 200, res.text
    entry = _log(client, action="invoice.create")[0]
    assert entry["actor"] == "asha"
    assert entry["detail"]["label"] == res.json()["invoice_number"]
    assert "Banner (8×4 ft, 2 @ 10)" in _changes(entry)["items"][1]


def test_editing_invoice_lines_shows_old_and_new(client, db, admin):
    invoice = create_invoice(db, InvoiceCreate(project_id=_project(db).id, items=[_line()]), "t")
    invoice_id = invoice.id
    _clear_log(db)

    res = client.patch(f"/invoices/{invoice_id}", json={"items": [_line("Banner", 25).model_dump()]})
    assert res.status_code == 200, res.text

    entries = _log(client, action="invoice.update")
    assert len(entries) == 1
    changes = _changes(entries[0])
    assert changes["items"] == ("Banner (8×4 ft, 2 @ 10)", "Banner (8×4 ft, 2 @ 25)")
    assert changes["amount"] == (640, 1600)


def test_a_payment_is_one_clear_entry_not_two(client, db, admin):
    invoice = create_invoice(db, InvoiceCreate(project_id=_project(db).id, items=[_line()]), "t")
    _clear_log(db)
    assert client.patch(f"/invoices/{invoice.id}/record-payment",
                        json={"amount": 250, "payment_method": "Cash"}).status_code == 200
    assert [e["action"] for e in _log(client)] == ["invoice.payment"]


def test_a_payment_shows_what_changed_to_what(client, db, admin):
    invoice = create_invoice(db, InvoiceCreate(project_id=_project(db).id, items=[_line()]), "t")
    assert client.patch(f"/invoices/{invoice.id}/record-payment",
                        json={"amount": 250, "payment_method": "Cash"}).status_code == 200
    assert _changes(_log(client, action="invoice.payment")[0]) == {"advance_amount": (0, 250)}


def test_the_payment_that_settles_an_invoice_shows_the_status_change_too(client, db, admin):
    invoice = create_invoice(db, InvoiceCreate(project_id=_project(db).id, items=[_line()]), "t")
    assert client.patch(f"/invoices/{invoice.id}/record-payment",
                        json={"amount": 640, "payment_method": "Cash"}).status_code == 200
    assert _changes(_log(client, action="invoice.payment")[0]) == {
        "advance_amount": (0, 640),
        "status": ("pending", "paid"),
    }


def test_marking_paid_shows_what_changed_to_what(client, db, admin):
    invoice = create_invoice(db, InvoiceCreate(project_id=_project(db).id, items=[_line()]), "t")
    assert client.patch(f"/invoices/{invoice.id}/mark-paid", json={"payment_method": "UPI"}).status_code == 200
    changes = _changes(_log(client, action="invoice.mark_paid")[0])
    assert changes["status"] == ("pending", "paid")
    assert changes["advance_amount"] == (0, 640)


def test_a_quotation_decision_shows_what_changed_to_what(client, db, admin):
    from app.entities import Quotation

    customer = Customer(first_name="Ravi", last_name="K", contact_number="9876543211")
    db.add(customer)
    db.commit()
    quotation = Quotation(quotation_number="QUOTE-1", customer_id=customer.id, project_type="Flex", subtotal=1, amount=1)
    db.add(quotation)
    db.commit()
    _clear_log(db)
    assert client.patch(f"/quotations/{quotation.id}/status", json={"status": "accepted"}).status_code == 200
    entries = _log(client)
    assert [e["action"] for e in entries] == ["quotation.accepted"]
    assert _changes(entries[0]) == {"status": ("pending", "accepted")}


def test_cancelling_is_one_clear_entry(client, db, admin):
    invoice = create_invoice(db, InvoiceCreate(project_id=_project(db).id, items=[_line()]), "t")
    _clear_log(db)
    assert client.patch(f"/invoices/{invoice.id}", json={"status": "cancelled"}).status_code == 200
    entries = _log(client)
    assert [e["action"] for e in entries] == ["invoice.cancel"]
    assert entries[0]["actor"] == "asha"
    assert _changes(entries[0]) == {"status": ("pending", "cancelled")}


# --- deletes --------------------------------------------------------------------


def test_each_project_in_a_bulk_delete_gets_its_own_named_entry(client, db, admin, uploads):
    first, second = _project(db, project_type="Flex"), _project(db, project_type="Standee")
    _clear_log(db)
    assert client.post("/projects/bulk-delete", json={"ids": [first.id, second.id]}).status_code == 200

    entries = _log(client)
    assert {(e["action"], e["entity_id"], e["detail"]["label"], e["actor"]) for e in entries} == {
        ("project.delete", first.id, "Flex", "asha"),
        ("project.delete", second.id, "Standee", "asha"),
    }


def test_deleted_files_are_logged_with_their_name(client, db, admin, uploads):
    project = _project(db)
    (uploads / "a.png").write_bytes(b"x")
    db.add(ProjectFile(project_id=project.id, path="a.png", original_name="Front banner.png"))
    db.commit()
    _clear_log(db)

    client.delete("/files/a.png")
    entry = _log(client)[0]
    assert (entry["action"], entry["detail"]["label"], entry["actor"]) == ("file.delete", "Front banner.png", "asha")
    assert entry["detail"]["info"] == f"From project #{project.id}"


def test_every_kind_of_delete_says_who_and_what(client, db, admin, uploads):
    company = Company(name="Acme")
    customer = Customer(first_name="Ravi", last_name="K", contact_number="9876543211")
    employee = User(username="suresh", email="s@example.com", phone="9876543212",
                    hashed_password="h", role=UserRole.USER, is_active=True)
    db.add_all([company, customer, employee])
    db.commit()
    _clear_log(db)

    client.delete(f"/companies/{company.id}")
    client.delete(f"/customers/{customer.id}")
    client.delete(f"/users/{employee.id}")

    entries = {e["action"]: e for e in _log(client)}
    assert entries["company.delete"]["detail"]["label"] == "Acme"
    assert entries["customer.delete"]["detail"]["label"] == "Ravi K"
    assert entries["user.delete"]["detail"]["label"] == "suresh"
    assert all(e["actor"] == "asha" for e in entries.values())
    assert len(entries) == 3


def test_a_refused_delete_logs_nothing(client, db, admin, uploads):
    project = _project(db)
    create_invoice(db, InvoiceCreate(project_id=project.id, items=[_line()]), "t")
    _clear_log(db)
    assert client.delete(f"/projects/{project.id}").status_code == 400
    assert _log(client) == []


def test_restoring_is_logged_once_without_looking_like_new_records(client, db, admin, uploads):
    project = _project(db)
    client.delete(f"/projects/{project.id}")
    item = client.get("/bin/").json()["items"][0]
    _clear_log(db)
    client.post(f"/bin/{item['id']}/restore")
    entries = _log(client)
    assert [e["action"] for e in entries] == ["bin.restore"]
    assert entries[0]["entity_type"] == "project"


def test_an_employee_restore_files_under_employee(client, db, admin, uploads):
    employee = User(username="suresh", email="s@example.com", phone="9876543212",
                    hashed_password="h", role=UserRole.USER, is_active=True)
    db.add(employee)
    db.commit()
    client.delete(f"/users/{employee.id}")
    client.post(f"/bin/{client.get('/bin/').json()['items'][0]['id']}/restore")
    assert _log(client)[0]["entity_type"] == "user"


def test_the_14_day_erasure_is_logged_as_automatic(client, db, admin, uploads):
    client.delete(f"/projects/{_project(db).id}")
    db.query(BinItem).one().expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert bin_service.erase_expired(db) == 1
    entry = _log(client)[0]
    assert (entry["action"], entry["actor"]) == ("bin.expire", "system")


# --- job type on Add Invoice -----------------------------------------------------


def test_a_new_job_invoice_doesnt_need_a_job_type(client, db, admin):
    customer = Customer(first_name="Ravi", last_name="K", contact_number="9876543211")
    db.add(customer)
    db.commit()
    res = client.post("/invoices/", json={"new_project": {"customer_id": customer.id}, "items": [_line().model_dump()]})
    assert res.status_code == 200, res.text
    assert db.query(Project).one().project_type == "General"


def test_a_blank_job_type_is_treated_as_none(client, db, admin):
    customer = Customer(first_name="Ravi", last_name="K", contact_number="9876543211")
    db.add(customer)
    db.commit()
    client.post("/invoices/", json={"new_project": {"project_type": "  ", "customer_id": customer.id}, "items": [_line().model_dump()]})
    assert db.query(Project).one().project_type == "General"


def test_a_chosen_job_type_is_kept(client, db, admin):
    customer = Customer(first_name="Ravi", last_name="K", contact_number="9876543211")
    db.add(customer)
    db.commit()
    client.post("/invoices/", json={"new_project": {"project_type": "Flex", "customer_id": customer.id}, "items": [_line().model_dump()]})
    assert db.query(Project).one().project_type == "Flex"


def test_a_customer_is_still_required(client, db, admin):
    res = client.post("/invoices/", json={"new_project": {"project_type": "Flex"}, "items": [_line().model_dump()]})
    assert res.status_code == 422


def test_opening_the_invoice_design_for_the_first_time_isnt_an_edit(client, db, admin):
    _clear_log(db)
    assert client.get("/document-settings/").status_code == 200
    assert _log(client) == []
