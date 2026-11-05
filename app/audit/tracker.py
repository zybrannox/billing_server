"""Records every change to the things people care about, with before, after and who.

Hooked into the database session rather than called from each route, so a route
added next year is covered without anyone remembering to log it. Entries are
written in the same transaction as the change: if the change rolls back, so does
its entry, and a change can't be saved without one.

Who did it comes from session.info["actor"], set by the login dependencies (see
app/auth/dependencies.py), since a request's session is shared with its route.

Deliberately not recorded by this hook:
- Actions with a richer entry of their own: payments, marking paid, cancelling,
  accepting or rejecting a quotation (see the controllers), moving to and restoring
  from the bin (see app/bin), which also bypass the ORM.
- Secrets (values of passwords, tokens and reset codes are never stored; a changed
  password is logged as just that) and bookkeeping nobody needs to see.
"""
import enum
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Optional

import sqlalchemy as sa
from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.auth.permissions import PERMISSION_LABELS
from app.database import SessionLocal
from app.entities import (
    AuditLog,
    ClientAccount,
    Company,
    Customer,
    DocumentSettings,
    Invoice,
    JobRequest,
    ListOption,
    Note,
    ProjectFile,
    Quotation,
    SharedDocument,
    User,
)
from app.entities.project import Project

logger = logging.getLogger("app.audit")

PENDING = "audit_pending"


def _customer_name(session: Session, customer_id: Optional[int]) -> Optional[str]:
    customer = session.get(Customer, customer_id) if customer_id else None
    return f"{customer.first_name} {customer.last_name}".strip() if customer else None


def _project_label(session: Session, p: Project) -> str:
    name = _customer_name(session, p.customer_id)
    return f"{p.project_type or f'Project #{p.id}'}{f' – {name}' if name else ''}"


def _invoice_label(session: Session, i: Invoice) -> str:
    return i.invoice_number or f"Invoice #{i.id}"


# Type name used in the log, and how to name a row of it.
_TRACKED: dict[type, tuple[str, Callable[[Session, Any], str]]] = {
    Project: ("project", _project_label),
    ProjectFile: ("file", lambda s, f: f.original_name or f.path),
    Invoice: ("invoice", _invoice_label),
    Quotation: ("quotation", lambda s, q: q.quotation_number or f"Quotation #{q.id}"),
    Customer: ("customer", lambda s, c: f"{c.first_name} {c.last_name}".strip()),
    Company: ("company", lambda s, c: c.name),
    User: ("user", lambda s, u: u.username),
    ListOption: ("list_option", lambda s, o: o.value),
    DocumentSettings: ("document_settings", lambda s, d: "Invoice design"),
    JobRequest: ("job_request", lambda s, j: f"Request #{j.id}"),
    ClientAccount: ("client_account", lambda s, a: a.email or f"Account #{a.id}"),
    SharedDocument: ("share_link", lambda s, d: f"{d.document_type.title()} #{d.document_id}"),
    Note: ("note", lambda s, n: (n.text.splitlines() or [f"Note #{n.id}"])[0][:120]),
}

# Never recorded for any type.
_BOOKKEEPING = {"id", "created_at", "updated_at", "failed_login_count", "locked_until", "last_login_at"}
_SECRET_WORDS = ("password", "token", "reset_code")

# Not recorded when these change on an existing row, because something else tells
# the story better or they mean nothing to a reader.
_QUIET_UPDATES: dict[type, set[str]] = {
    # Each payment, marking paid and cancelling has its own entry.
    Invoice: {"status", "advance_amount", "payment_method", "payment_reference", "paid_at"},
    # Accepting and rejecting have their own entries; converting is shown by the
    # project and invoice it creates.
    Quotation: {"status", "converted_project_id", "converted_invoice_id"},
    ProjectFile: {"downloaded"},
    # A job being done or not is the one thing worth showing; these follow from it.
    Note: {"done_at", "done_by", "invoice_id"},
}
# Not shown in what a new row was created with: plumbing, or hidden from the app.
_QUIET_ON_CREATE: dict[type, set[str]] = {
    Invoice: {"invoice_number", "project_id"},
    Quotation: {"quotation_number"},
    ProjectFile: {"path", "width", "height", "pixel_width", "pixel_height", "downloaded"},
    SharedDocument: {"filename", "expires_at"},
    Note: {"created_by", "is_done", "invoice_id"},
}
# Priority is no longer offered anywhere in the app (the values stay stored).
_HIDDEN: dict[type, set[str]] = {Project: {"priority"}}
# Created automatically the first time they're read, not by anyone's action.
_NO_CREATE_ENTRY = {DocumentSettings}

_LABELS = {
    "project_type": "Job type",
    "assigned_to": "Assigned to",
    "client_status": "Client status",
    "print_status": "Print status",
    "start_date": "Start date",
    "delivery_date": "Delivery date",
    "customer_id": "Customer",
    "company_id": "Company",
    "project_id": "Project",
    "pinned": "Pinned",
    "delivered_on_credit": "Delivered on credit",
    "design_completed_at": "Design completed",
    "design_completed_by": "Design completed by",
    "print_completed_at": "Print completed",
    "print_completed_by": "Print completed by",
    "delivered_at": "Delivered",
    "delivered_by": "Delivered by",
    "notified_at": "Client notified",
    "notified_by": "Client notified by",
    "discount_amount": "Discount",
    "advance_amount": "Advance",
    "amount": "Total",
    "due_date": "Due date",
    "valid_until": "Valid until",
    "contact_number": "Contact number",
    "first_name": "First name",
    "last_name": "Last name",
    "is_active": "Active",
    "original_name": "File name",
    "original_deleted_at": "Original file removed",
    "value": "Name",
    "rate": "Default rate",
    "items": "Line items",
    "reviewed_by": "Reviewed by",
    "reviewed_at": "Reviewed",
    "rejection_reason": "Rejection reason",
    "activated_at": "Activated",
    "invited_at": "Invited",
    "invited_by": "Invited by",
    "billing_email": "Billing email",
    "billing_address": "Billing address",
    "payment_terms_days": "Payment terms (days)",
    "credit_limit": "Credit limit",
    "document_type": "Document",
    "document_id": "Document number",
    "permissions": "Access",
    "min_charges": "Minimum charges",
    "is_done": "Job done",
    "text": "Note",
}


def _label_of(field: str) -> str:
    return _LABELS.get(field) or field.removesuffix("_id").replace("_", " ").capitalize()


def _plain(column: Optional[sa.Column], value: Any) -> Any:
    """A JSON-safe value that compares equal when the real value is the same: an
    edit form often sends a date back as text, which isn't a change."""
    if isinstance(column.type if column is not None else None, sa.DateTime) and isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.isoformat() + "Z"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, Decimal):
        return float(value)
    return value


def _lines_text(items: list) -> Optional[str]:
    lines = []
    for item in items:
        size = f"{item.width:g}×{item.height:g} {item.unit}, " if getattr(item, "has_dimensions", True) else ""
        lines.append(f"{item.description or 'Item'} ({size}{item.pieces} @ {item.rate:g})")
    return "; ".join(lines)[:1000] or None


def _trackable_columns(cls: type):
    for attr in inspect(cls).column_attrs:
        name = attr.key
        if name in _BOOKKEEPING or name in _HIDDEN.get(cls, set()):
            continue
        if any(word in name for word in _SECRET_WORDS) and name != "hashed_password":
            continue
        yield name, attr.columns[0]


def _stored_value(session: Session, obj: Any, column: sa.Column) -> Any:
    """The value in the database right now. After a commit a row's values are
    forgotten, so changing one leaves nothing in memory to compare against."""
    table = column.table
    return session.execute(sa.select(column).where(table.c.id == obj.id)).scalar_one_or_none()


def _entry(session: Session, obj: Any, verb: str) -> dict:
    pending = session.info.setdefault(PENDING, {})
    return pending.setdefault((type(obj), id(obj)), {"obj": obj, "verb": verb, "changes": {}, "label": None})


def _note_update(session: Session, obj: Any) -> None:
    cls = type(obj)
    state = inspect(obj)
    quiet = _QUIET_UPDATES.get(cls, set())
    for name, column in _trackable_columns(cls):
        if name in quiet:
            continue
        history = state.attrs[name].history
        if not history.added:
            continue
        before = history.deleted[0] if history.deleted else _stored_value(session, obj, column)
        after = history.added[0]
        entry = _entry(session, obj, "update")
        if name == "hashed_password":
            entry["changes"].setdefault(name, {"hidden": True, "from": 0, "to": 1})
            continue
        # The first "before" and the last "after", across several saves.
        change = entry["changes"].setdefault(name, {"from": _plain(column, before)})
        change["to"] = _plain(column, after)

    if cls in (Invoice, Quotation):
        items = state.attrs["items"].history
        if items.added or items.deleted:
            before = _lines_text(list(items.unchanged or []) + list(items.deleted or []))
            after = _lines_text(list(items.unchanged or []) + list(items.added or []))
            entry = _entry(session, obj, "update")
            change = entry["changes"].setdefault("items", {"from": before})
            change["to"] = after


def _before_flush(session: Session, _context: Any, _instances: Any) -> None:
    try:
        with session.no_autoflush:
            for obj in session.dirty:
                if type(obj) in _TRACKED and session.is_modified(obj):
                    _note_update(session, obj)
            for obj in session.deleted:
                if type(obj) in _TRACKED:
                    entry = _entry(session, obj, "delete")
                    entry["verb"] = "delete"
                    entry["id"] = obj.id
                    entry["label"] = _TRACKED[type(obj)][1](session, obj)
    except Exception:  # pragma: no cover - a log entry must never block the work
        logger.exception("Couldn't work out what changed")


def _after_flush(session: Session, _context: Any) -> None:
    # Here rather than before the flush because a new row has no id until now.
    for obj in session.new:
        if type(obj) in _TRACKED and type(obj) not in _NO_CREATE_ENTRY:
            _entry(session, obj, "create")


def _shown(session: Session, field: str, value: Any) -> Any:
    if value is None:
        return None
    if field == "customer_id":
        return _customer_name(session, value) or f"#{value}"
    if field == "company_id":
        company = session.get(Company, value)
        return company.name if company else f"#{value}"
    if field in ("project_id", "document_id"):
        return f"#{value}"
    if field == "permissions":
        return ", ".join(PERMISSION_LABELS.get(p, p) for p in value) or "None"
    if field == "min_charges":
        return ", ".join(f"Rs {t['amount']:g} up to {t['up_to_sq_ft']:g} sq ft" for t in value) or "None"
    return value


def _created_with(session: Session, obj: Any) -> list[dict]:
    cls = type(obj)
    quiet = _QUIET_ON_CREATE.get(cls, set())
    changes = []
    for name, column in _trackable_columns(cls):
        if name in quiet or name == "hashed_password":
            continue
        value = _plain(column, getattr(obj, name))
        # An empty or switched-off field says nothing about what was created.
        if value in (None, "", 0, False) or value == []:
            continue
        changes.append({"field": name, "label": _label_of(name), "from": None, "to": _shown(session, name, value)})
    if cls in (Invoice, Quotation) and obj.items:
        changes.append({"field": "items", "label": _label_of("items"), "from": None, "to": _lines_text(obj.items)})
    return changes


def _row(session: Session, entry: dict) -> Optional[dict]:
    obj, verb = entry["obj"], entry["verb"]
    cls = type(obj)
    type_name, name_of = _TRACKED[cls]

    if verb == "create":
        changes = _created_with(session, obj)
    elif verb == "update":
        changes = []
        for field, change in entry["changes"].items():
            if change.get("hidden"):
                changes.append({"field": field, "label": "Password", "hidden": True})
            elif change["from"] != change["to"]:
                changes.append(
                    {
                        "field": field,
                        "label": _label_of(field),
                        "from": _shown(session, field, change["from"]),
                        "to": _shown(session, field, change["to"]),
                    }
                )
        if not changes:
            return None  # saved, but nothing actually different
    else:
        changes = []

    actor = session.info.get("actor")
    if not actor:
        # Nobody signed in. Resetting your own password is you, not the system.
        if verb == "update" and cls is User:
            actor = obj.username
        elif verb == "update" and cls is ClientAccount:
            actor = f"client:{obj.email}"
        else:
            actor = "system"

    entity_id = entry.get("id", getattr(obj, "id", None))
    label = entry["label"] or name_of(session, obj)
    return {
        "actor": actor,
        "action": f"{type_name}.{verb}",
        "entity_type": type_name,
        "entity_id": entity_id,
        "detail": {"label": label, "changes": changes},
    }


def _before_commit(session: Session) -> None:
    # Outside the guard: a failure to save is the caller's to handle as usual.
    session.flush()
    pending = session.info.pop(PENDING, None)
    if not pending:
        return
    try:
        with session.no_autoflush:
            rows = [row for entry in pending.values() if (row := _row(session, entry))]
        if rows:
            session.connection().execute(sa.insert(AuditLog.__table__), rows)
    except Exception:  # pragma: no cover - a log entry must never block the work
        logger.exception("Couldn't write the activity log")


def _after_rollback(session: Session) -> None:
    session.info.pop(PENDING, None)


def install() -> None:
    event.listen(SessionLocal, "before_flush", _before_flush)
    event.listen(SessionLocal, "after_flush", _after_flush)
    event.listen(SessionLocal, "before_commit", _before_commit)
    event.listen(SessionLocal, "after_rollback", _after_rollback)
