"""Who may do what is decided on the server; notes get ticked off and billed."""
import pytest
from passlib.hash import bcrypt

from app.datetime_utils import utcnow
from app.entities import AuditLog, Customer, Invoice, ListOption, Note, User, UserRole
from app.entities.project import Project
from app.invoices.model import InvoiceCreate, InvoiceItemCreate
from app.invoices.repository import create_invoice
from app.security import create_access_token

LINE = {"description": "Banner", "width": 8, "height": 4, "rate": 10, "pieces": 2, "unit": "ft"}


def _user(db, name, role=UserRole.USER, permissions=None):
    user = User(username=name, email=f"{name}@example.com", phone=str(9000000000 + abs(hash(name)) % 999999999)[:10],
                hashed_password=bcrypt.hash("x" * 12), role=role, is_active=True, permissions=permissions or [])
    db.add(user)
    db.commit()
    return user


def _sign_in(client, user):
    client.cookies.set("access_token", create_access_token({"sub": user.username, "role": user.role.value, "tv": 0}))
    client.headers["X-Requested-With"] = "XMLHttpRequest"


@pytest.fixture
def admin(client, db):
    user = _user(db, "boss", UserRole.ADMIN)
    _sign_in(client, user)
    return user


@pytest.fixture
def employee(client, db):
    user = _user(db, "ravi")
    _sign_in(client, user)
    return user


@pytest.fixture
def note_taker(client, db):
    user = _user(db, "ravi", permissions=["notes.access"])
    _sign_in(client, user)
    return user


def _customer(db):
    customer = Customer(first_name="Meera", last_name="S", contact_number="9876543212")
    db.add(customer)
    db.commit()
    return customer


def _project(db):
    now = utcnow()
    project = Project(project_type="Flex", assigned_to="ravi", priority="Normal", client_status="Confirmed",
                      print_status="In Progress", start_date=now, delivery_date=now)
    db.add(project)
    db.commit()
    return project


def _invoice(db):
    return create_invoice(db, InvoiceCreate(project_id=_project(db).id, items=[InvoiceItemCreate(**LINE)]), "t")


def _grant(db, user, *permissions):
    user.permissions = list(permissions)
    db.commit()


# --- what /auth/me says -----------------------------------------------------------


def test_admins_have_everything(client, admin):
    assert set(client.get("/auth/me").json()["permissions"]) == {
        "invoice.create", "invoice.edit", "workspace.manage", "notes.access",
    }


def test_employees_start_with_nothing(client, employee):
    assert client.get("/auth/me").json()["permissions"] == []


def test_employees_see_what_they_were_granted(client, db, employee):
    _grant(db, employee, "invoice.edit")
    assert client.get("/auth/me").json()["permissions"] == ["invoice.edit"]


# --- new invoices -----------------------------------------------------------------


def test_new_invoice_is_refused_without_access(client, db, employee):
    res = client.post("/invoices/", json={"project_id": _project(db).id, "items": [LINE]})
    assert res.status_code == 403
    assert "Ask an admin" in res.json()["detail"]
    assert db.query(Invoice).count() == 0


def test_new_invoice_works_with_access(client, db, employee):
    _grant(db, employee, "invoice.create")
    assert client.post("/invoices/", json={"project_id": _project(db).id, "items": [LINE]}).status_code == 200


def test_access_can_be_taken_away_again(client, db, employee):
    _grant(db, employee, "invoice.create")
    _grant(db, employee)
    assert client.post("/invoices/", json={"project_id": _project(db).id, "items": [LINE]}).status_code == 403


def test_a_quotation_cant_be_converted_without_access(client, db, employee):
    now = utcnow().isoformat() + "Z"
    res = client.post("/quotations/1/convert", json={"assigned_to": "a", "client_status": "Confirmed", "start_date": now, "delivery_date": now})
    assert res.status_code == 403


def test_finishing_a_design_still_works_without_invoice_access(client, db, employee):
    project = _project(db)
    assert client.patch(f"/projects/{project.id}/design-completed").status_code == 200


# --- editing invoices --------------------------------------------------------------


def test_editing_is_refused_without_access(client, db, employee):
    invoice = _invoice(db)
    assert client.patch(f"/invoices/{invoice.id}", json={"items": [LINE]}).status_code == 403


def test_create_access_doesnt_include_edit(client, db, employee):
    invoice = _invoice(db)
    _grant(db, employee, "invoice.create")
    assert client.patch(f"/invoices/{invoice.id}", json={"items": [LINE]}).status_code == 403


def test_editing_works_with_access(client, db, employee):
    invoice = _invoice(db)
    _grant(db, employee, "invoice.edit")
    assert client.patch(f"/invoices/{invoice.id}", json={"items": [{**LINE, "rate": 25}]}).status_code == 200


def test_edit_access_doesnt_allow_cancelling(client, db, employee):
    invoice = _invoice(db)
    _grant(db, employee, "invoice.edit")
    res = client.patch(f"/invoices/{invoice.id}", json={"status": "cancelled"})
    assert res.status_code == 403
    db.refresh(invoice)
    assert invoice.status == "pending"


def test_admin_can_still_cancel(client, db, admin):
    invoice = _invoice(db)
    assert client.patch(f"/invoices/{invoice.id}", json={"status": "cancelled"}).status_code == 200


def test_edit_access_doesnt_allow_deleting(client, db, employee):
    invoice = _invoice(db)
    _grant(db, employee, "invoice.edit", "invoice.create", "workspace.manage")
    assert client.delete(f"/invoices/{invoice.id}").status_code == 403


# --- workspace settings -------------------------------------------------------------


def test_workspace_settings_are_refused_without_access(client, db, employee):
    assert client.post("/list-options/", json={"category": "item_type", "value": "Flex"}).status_code == 403
    assert client.put("/document-settings/", json={"business_name": "X"}).status_code == 403


def test_workspace_settings_work_with_access(client, db, employee):
    _grant(db, employee, "workspace.manage")
    res = client.post("/list-options/", json={"category": "item_type", "value": "Flex", "rate": 10})
    assert res.status_code == 200, res.text
    assert client.patch(f"/list-options/{res.json()['id']}/deactivate").status_code == 200
    settings = client.get("/document-settings/").json()
    settings["business_name"] = "New name"
    res = client.put("/document-settings/", json=settings)
    assert res.status_code == 200, res.text
    assert res.json()["business_name"] == "New name"


@pytest.mark.parametrize("method,path", [
    ("get", "/bin/"),
    ("get", "/audit-log/"),
    ("get", "/system-health"),
    ("put", "/users/1/permissions"),
])
def test_workspace_access_doesnt_reach_the_admin_only_sections(client, db, employee, method, path):
    _grant(db, employee, "workspace.manage", "invoice.create", "invoice.edit")
    kwargs = {"json": {"permissions": ["workspace.manage"]}} if method == "put" else {}
    assert getattr(client, method)(path, **kwargs).status_code == 403


# --- granting -----------------------------------------------------------------------


def test_admin_grants_and_the_log_says_so(client, db, admin):
    employee = _user(db, "ravi")
    db.query(AuditLog).delete()
    db.commit()

    res = client.put(f"/users/{employee.id}/permissions", json={"permissions": ["invoice.edit", "invoice.create"]})
    assert res.status_code == 200
    assert res.json()["permissions"] == ["invoice.create", "invoice.edit"]

    entry = client.get("/audit-log/").json()["items"][0]
    assert (entry["action"], entry["actor"]) == ("user.update", "boss")
    change = entry["detail"]["changes"][0]
    assert (change["label"], change["from"], change["to"]) == ("Access", "None", "New invoices, Edit invoices")


def test_an_employee_cant_grant_themselves_access(client, db, employee):
    assert client.put(f"/users/{employee.id}/permissions", json={"permissions": ["invoice.create"]}).status_code == 403


def test_an_unknown_permission_is_rejected(client, db, admin):
    employee = _user(db, "ravi")
    assert client.put(f"/users/{employee.id}/permissions", json={"permissions": ["everything"]}).status_code == 422


# --- notes --------------------------------------------------------------------------


def _note(client, text="Flex banner 8x4 for Meera", **kw):
    res = client.post("/notes/", json={"text": text, **kw})
    assert res.status_code == 200, res.text
    return res.json()


def test_an_employee_with_access_can_add_a_note(client, db, note_taker):
    note = _note(client)
    assert (note["text"], note["created_by"], note["is_done"]) == ("Flex banner 8x4 for Meera", "ravi", False)


def test_a_blank_note_is_refused(client, db, note_taker):
    assert client.post("/notes/", json={"text": "   "}).status_code == 422


def test_notes_need_a_login(client):
    assert client.get("/notes/").status_code == 401


def test_a_note_can_have_a_customer(client, db, note_taker):
    customer = _customer(db)
    assert _note(client, customer_id=customer.id)["customer_name"] == "Meera S"
    assert client.post("/notes/", json={"text": "x", "customer_id": 9999}).status_code == 404


def test_clicking_done_records_who_and_when_and_clicking_again_undoes_it(client, db, note_taker):
    note = _note(client)
    done = client.patch(f"/notes/{note['id']}", json={"is_done": True}).json()
    assert done["is_done"] is True
    assert done["done_by"] == "ravi"
    assert done["done_at"]

    undone = client.patch(f"/notes/{note['id']}", json={"is_done": False}).json()
    assert undone["is_done"] is False
    assert undone["done_by"] is None
    assert undone["done_at"] is None


def test_notes_can_be_edited(client, db, note_taker):
    note = _note(client)
    assert client.patch(f"/notes/{note['id']}", json={"text": "Changed"}).json()["text"] == "Changed"


def test_whats_still_to_do_comes_first_with_counts(client, db, note_taker):
    first, second, third = _note(client, "first"), _note(client, "second"), _note(client, "third")
    client.patch(f"/notes/{third['id']}", json={"is_done": True})

    body = client.get("/notes/").json()
    assert [n["text"] for n in body["items"]] == ["second", "first", "third"]
    assert (body["open_count"], body["done_count"]) == (2, 1)
    assert [n["text"] for n in client.get("/notes/?status=done").json()["items"]] == ["third"]
    assert client.get("/notes/?status=open").json()["total"] == 2
    assert client.get("/notes/?status=done").json()["open_count"] == 2


def test_a_note_can_become_an_invoice_and_shows_its_number(client, db, note_taker):
    _grant(db, note_taker, "notes.access", "invoice.create")
    customer = _customer(db)
    note = _note(client)
    res = client.post("/invoices/", json={"new_project": {"customer_id": customer.id}, "note_id": note["id"], "items": [LINE]})
    assert res.status_code == 200, res.text

    item = client.get("/notes/").json()["items"][0]
    assert item["invoice_id"] == res.json()["id"]
    assert item["invoice_number"] == res.json()["invoice_number"]


def test_a_note_cant_be_billed_twice(client, db, note_taker):
    _grant(db, note_taker, "notes.access", "invoice.create")
    customer = _customer(db)
    note = _note(client)
    payload = {"new_project": {"customer_id": customer.id}, "note_id": note["id"], "items": [LINE]}
    assert client.post("/invoices/", json=payload).status_code == 200
    res = client.post("/invoices/", json=payload)
    assert res.status_code == 400
    assert "already" in res.json()["detail"]


def test_billing_a_note_needs_invoice_access(client, db, note_taker):
    customer = _customer(db)
    note = _note(client)
    res = client.post("/invoices/", json={"new_project": {"customer_id": customer.id}, "note_id": note["id"], "items": [LINE]})
    assert res.status_code == 403
    assert db.get(Note, note["id"]).invoice_id is None


def test_deleting_a_note_goes_to_the_bin_and_can_be_restored(client, db, admin):
    note = _note(client, "Line one\nLine two")
    assert client.delete(f"/notes/{note['id']}").status_code == 200
    assert client.get("/notes/").json()["total"] == 0

    item = client.get("/bin/").json()["items"][0]
    assert (item["item_type"], item["label"]) == ("note", "Line one")
    assert client.post(f"/bin/{item['id']}/restore").status_code == 200
    assert client.get("/notes/").json()["items"][0]["text"] == "Line one\nLine two"


def test_deleting_the_customer_keeps_the_note(client, db, admin):
    customer = _customer(db)
    note = _note(client, customer_id=customer.id)
    assert client.delete(f"/customers/{customer.id}").status_code == 200
    assert client.get("/notes/").json()["items"][0]["id"] == note["id"]
    assert client.get("/notes/").json()["items"][0]["customer_name"] is None


def test_notes_are_in_the_activity_log(client, db, admin):
    note = _note(client)
    client.patch(f"/notes/{note['id']}", json={"is_done": True})
    entries = client.get("/audit-log/?entity_type=note").json()["items"]
    assert [e["action"] for e in entries] == ["note.update", "note.create"]
    assert entries[0]["actor"] == "boss"
    change = entries[0]["detail"]["changes"][0]
    assert (change["label"], change["from"], change["to"]) == ("Job done", False, True)
