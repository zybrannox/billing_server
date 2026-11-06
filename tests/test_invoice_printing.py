"""The invoice Print button goes straight to the connected printer, with no dialog."""
import subprocess

import pytest
from passlib.hash import bcrypt

from app.datetime_utils import utcnow
from app.entities import AuditLog, Invoice, User, UserRole
from app.entities.project import Project
from app.invoices import printing
from app.invoices.controller import MAX_PRINT_BYTES
from app.security import create_access_token

PDF = b"%PDF-1.7 a real invoice"


@pytest.fixture
def employee(client, db):
    user = User(username="ravi", email="ravi@example.com", phone="9000000001",
                hashed_password=bcrypt.hash("x" * 12), role=UserRole.USER, is_active=True, permissions=[])
    db.add(user)
    db.commit()
    client.cookies.set("access_token", create_access_token({"sub": "ravi", "role": "user", "tv": 0}))
    client.headers["X-Requested-With"] = "XMLHttpRequest"
    return user


@pytest.fixture
def invoice(db):
    now = utcnow()
    project = Project(project_type="Flex", assigned_to="ravi", priority="Normal", client_status="Confirmed",
                      print_status="In Progress", start_date=now, delivery_date=now)
    db.add(project)
    db.flush()
    invoice = Invoice(project_id=project.id, invoice_number="INV-2026-00001", status="pending",
                      subtotal=100, discount_amount=0, amount=100, advance_amount=0)
    db.add(invoice)
    db.commit()
    return invoice


class Machine:
    """Stands in for macOS's print commands, so no test ever uses real paper."""

    def __init__(self):
        self.default = b"system default destination: HP_LaserJet\n"
        self.state = b"printer HP_LaserJet is idle.  enabled since today\n"
        self.lp_exit = 0
        self.printed = []

    def run(self, command, input=None, **kwargs):
        if command[:2] == ["lpstat", "-d"]:
            return subprocess.CompletedProcess(command, 0, self.default, b"")
        if command[:2] == ["lpstat", "-p"]:
            return subprocess.CompletedProcess(command, 0, self.state, b"")
        assert command[0] == "lp"
        self.printed.append((command, input))
        return subprocess.CompletedProcess(command, self.lp_exit, b"request id is HP_LaserJet-1", b"lp said no")


@pytest.fixture
def machine(monkeypatch):
    fake = Machine()
    monkeypatch.setattr(printing.subprocess, "run", fake.run)
    return fake


def _print(client, invoice_id, data=PDF):
    return client.post(f"/invoices/{invoice_id}/print", files={"file": ("invoice.pdf", data, "application/pdf")})


def test_printing_needs_a_login(client, invoice, machine):
    assert _print(client, invoice.id).status_code == 401
    assert machine.printed == []


def test_any_employee_can_print_to_the_connected_printer(client, db, employee, invoice, machine):
    res = _print(client, invoice.id)
    assert res.status_code == 200, res.text
    assert res.json() == {"printer": "HP_LaserJet"}
    command, data = machine.printed[0]
    assert command[:3] == ["lp", "-d", "HP_LaserJet"]
    assert "INV-2026-00001" in command
    assert data == PDF


def test_printing_is_logged(client, db, employee, invoice, machine):
    _print(client, invoice.id)
    assert db.query(AuditLog).filter_by(action="invoice.print", actor="ravi").count() == 1


def test_a_missing_invoice_prints_nothing(client, employee, machine):
    assert _print(client, 9999).status_code == 404
    assert machine.printed == []


def test_only_a_pdf_can_be_printed(client, employee, invoice, machine):
    assert _print(client, invoice.id, b"<html>not a pdf</html>").status_code == 400
    assert machine.printed == []


def test_an_oversized_file_is_refused(client, employee, invoice, machine):
    assert _print(client, invoice.id, PDF + b"x" * MAX_PRINT_BYTES).status_code == 413
    assert machine.printed == []


@pytest.mark.parametrize("default", [b"no system default destination\n", b""])
def test_no_printer_set_up_says_so(client, db, employee, invoice, machine, default):
    machine.default = default
    res = _print(client, invoice.id)
    assert res.status_code == 503
    assert "No printer" in res.json()["detail"]
    assert db.query(AuditLog).filter_by(action="invoice.print").count() == 0


@pytest.mark.parametrize("state", [b"printer HP_LaserJet disabled since today -\n\tPaused\n", b""])
def test_a_paused_printer_isnt_given_a_job_to_hold(client, employee, invoice, machine, state):
    machine.state = state
    res = _print(client, invoice.id)
    assert res.status_code == 503
    assert "off or paused" in res.json()["detail"]
    assert machine.printed == []


def test_a_refused_job_says_so_without_leaking_details(client, employee, invoice, machine):
    machine.lp_exit = 1
    res = _print(client, invoice.id)
    assert res.status_code == 503
    assert "lp said no" not in res.text


def test_a_stuck_printer_command_doesnt_hang_the_request(client, employee, invoice, monkeypatch):
    def run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 1)

    monkeypatch.setattr(printing.subprocess, "run", run)
    assert _print(client, invoice.id).status_code == 503


def test_printing_is_rate_limited(client, employee, invoice, machine):
    codes = [_print(client, invoice.id).status_code for _ in range(31)]
    assert codes == [200] * 30 + [429]
