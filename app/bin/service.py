"""The bin: deleted things are kept for 14 days, then erased.

Deleting takes a snapshot of the record and everything that belongs to it, then
removes the real rows. Nothing else in the app needs to know the bin exists: a
binned project can't turn up in a list or a total, because it isn't in the table.

What belongs to a record comes from the database's own foreign keys, so a table
added later is covered without touching this file:
- ON DELETE CASCADE children are part of the record and go in the snapshot.
- ON DELETE SET NULL references are remembered, so restoring can re-link them
  (a company's contacts, a job request's project).
- Any other reference means the record is still in use, and it can't be deleted.

Files move to uploads/.bin/<id>/ rather than being erased, thumbnails included.
"""
import enum
import logging
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Optional

import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import Base
from app.datetime_utils import utcnow
from app.entities import AuditLog, BinItem
from app.errors import NotFound

logger = logging.getLogger("app.bin")

BIN_RETENTION_DAYS = 14

UPLOAD_DIR = Path("./uploads")
# Tables whose rows each own an uploaded file, named by this column.
_FILE_COLUMNS = {"project_files": "path", "job_request_files": "path"}
# How a table's parent is described to the person restoring.
_TABLE_WORDS = {
    "projects": "project",
    "customers": "customer",
    "companies": "company",
    "invoices_v1": "invoice",
    "quotations": "quotation",
    "job_requests": "job request",
    "project_files": "file",
}


# The activity log's name for a type, where it differs.
_LOG_TYPES = {"employee": "user"}


def log_type(item_type: str) -> str:
    return _LOG_TYPES.get(item_type, item_type)


@dataclass
class BinEntry:
    item_type: str
    record: Any  # the ORM row being deleted
    label: str
    detail: Optional[str] = None


def _bin_dir(item_id: int) -> Path:
    return UPLOAD_DIR / ".bin" / str(item_id)


def _encode(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, enum.Enum):
        return value.name
    return value


def _decode(column: sa.Column, value: Any) -> Any:
    if value is None:
        return None
    kind = column.type
    if isinstance(kind, sa.DateTime):
        return datetime.fromisoformat(value)
    if isinstance(kind, sa.Date):
        return date.fromisoformat(value)
    if isinstance(kind, sa.Enum) and kind.enum_class:
        return kind.enum_class[value]
    if isinstance(kind, sa.Numeric) and isinstance(value, str):
        return Decimal(value)
    return value


def _references_to(table: sa.Table) -> Iterable[tuple[sa.Table, sa.ForeignKey]]:
    for other in Base.metadata.sorted_tables:
        for fk in other.foreign_keys:
            if fk.column.table is table:
                yield other, fk


def _capture(db: Session, record: Any) -> tuple[list[dict], list[dict], list[tuple[str, int]]]:
    """Returns (rows parents first, links to re-create, outside rows still using it)."""
    rows: list[dict] = []
    links: list[dict] = []
    captured: set[tuple[str, int]] = set()
    in_use: list[tuple[str, int]] = []

    def walk(table: sa.Table, row_id: int) -> None:
        key = (table.name, row_id)
        if key in captured:
            return
        captured.add(key)
        row = db.execute(sa.select(table).where(table.c.id == row_id)).mappings().one()
        rows.append({"table": table.name, "values": {k: _encode(v) for k, v in row.items()}})

        for child_table, fk in _references_to(table):
            if fk.column.name != "id":
                continue
            referencing = db.execute(
                sa.select(child_table.c.id).where(fk.parent == row_id)
            ).scalars().all()
            for child_id in referencing:
                action = (fk.ondelete or "").upper()
                if action == "CASCADE":
                    walk(child_table, child_id)
                elif action == "SET NULL":
                    links.append({"table": child_table.name, "id": child_id, "column": fk.parent.name, "value": row_id})
                else:
                    in_use.append((child_table.name, child_id))

    walk(record.__table__, record.id)
    still_in_use = [ref for ref in in_use if ref not in captured]
    outside_links = [l for l in links if (l["table"], l["id"]) not in captured]
    return rows, outside_links, still_in_use


def _table(name: str) -> sa.Table:
    return Base.metadata.tables[name]


def _files_of(rows: list[dict]) -> list[str]:
    return [
        row["values"][_FILE_COLUMNS[row["table"]]]
        for row in rows
        if row["table"] in _FILE_COLUMNS and row["values"].get(_FILE_COLUMNS[row["table"]])
    ]


def _file_locations(item_id: int, name: str) -> list[tuple[Path, Path]]:
    """(live location, location in the bin) for a file and its thumbnail."""
    # Stored names are generated by the server, but this does move files around.
    safe = Path(name).name
    held = _bin_dir(item_id)
    return [
        (UPLOAD_DIR / safe, held / safe),
        (UPLOAD_DIR / "thumbnails" / safe, held / "thumbnails" / safe),
    ]


def _move_files(moves: list[tuple[Path, Path]]) -> list[tuple[Path, Path]]:
    """Moves what exists (the retention job may already have removed an original)
    and returns what was moved, so a failure can put it all back."""
    done: list[tuple[Path, Path]] = []
    for source, target in moves:
        if source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            source.rename(target)
            done.append((source, target))
    return done


def _undo_moves(done: list[tuple[Path, Path]]) -> None:
    for source, target in done:
        try:
            target.rename(source)
        except OSError:  # pragma: no cover - defensive
            logger.exception("Couldn't put %s back", source)


def move_to_bin(
    db: Session,
    entries: list[BinEntry],
    deleted_by: str,
    in_use_message: str = "This is still in use elsewhere and can't be deleted.",
) -> list[BinItem]:
    """Deletes these records into the bin, together: all of them or none."""
    now = utcnow()
    staged = []
    for entry in entries:
        rows, links, in_use = _capture(db, entry.record)
        if in_use:
            raise HTTPException(status_code=400, detail=in_use_message)
        staged.append((entry, rows, links))

    items: list[BinItem] = []
    moved: list[tuple[Path, Path]] = []
    try:
        for entry, rows, links in staged:
            names = _files_of(rows)
            item = BinItem(
                item_type=entry.item_type,
                item_id=entry.record.id,
                label=entry.label[:500],
                detail=entry.detail[:500] if entry.detail else None,
                snapshot={"rows": rows, "links": links},
                size_bytes=sum(
                    (UPLOAD_DIR / Path(n).name).stat().st_size for n in names if (UPLOAD_DIR / Path(n).name).is_file()
                ),
                deleted_by=deleted_by,
                deleted_at=now,
                expires_at=now + timedelta(days=BIN_RETENTION_DAYS),
            )
            db.add(item)
            db.flush()

            logged = log_type(entry.item_type)
            db.add(
                AuditLog(
                    actor=deleted_by,
                    action=f"{logged}.delete",
                    entity_type=logged,
                    entity_id=entry.record.id,
                    detail={
                        "label": item.label,
                        "info": item.detail,
                        "size_bytes": item.size_bytes,
                        "note": f"Moved to the bin, kept for {BIN_RETENTION_DAYS} days",
                    },
                )
            )

            for link in links:
                table = _table(link["table"])
                db.execute(sa.update(table).where(table.c.id == link["id"]).values({link["column"]: None}))
            # Children first. Explicit rather than relying on the database's
            # cascades, so what's deleted is exactly what was captured.
            for row in reversed(rows):
                table = _table(row["table"])
                db.execute(sa.delete(table).where(table.c.id == row["values"]["id"]))

            for name in names:
                moved += _move_files(_file_locations(item.id, name))
            items.append(item)

        db.commit()
    except IntegrityError as err:
        db.rollback()
        _undo_moves(moved)
        raise HTTPException(status_code=400, detail=in_use_message) from err
    except Exception:
        db.rollback()
        _undo_moves(moved)
        raise

    db.expire_all()
    return items


def restore(db: Session, item_id: int) -> BinItem:
    item = db.get(BinItem, item_id)
    if not item:
        raise NotFound("Bin item")

    rows = item.snapshot["rows"]
    in_snapshot = {(r["table"], r["values"]["id"]) for r in rows}

    moved: list[tuple[Path, Path]] = []
    try:
        # Parents first, the order they were captured in.
        for row in rows:
            table = _table(row["table"])
            values = {c.name: _decode(c, row["values"].get(c.name)) for c in table.columns}
            for column in table.columns:
                for fk in column.foreign_keys:
                    parent_id = values.get(column.name)
                    if parent_id is None or (fk.column.table.name, parent_id) in in_snapshot:
                        continue
                    parent = fk.column.table
                    if db.execute(sa.select(parent.c.id).where(parent.c.id == parent_id)).first():
                        continue
                    # What it pointed at has gone since (and was itself deleted).
                    if column.nullable:
                        values[column.name] = None
                    else:
                        word = _TABLE_WORDS.get(parent.name, "linked record")
                        raise HTTPException(
                            status_code=409,
                            detail=f"This can't be restored because its {word} is no longer here. "
                            f"Restore the {word} from the bin first.",
                        )
            db.execute(sa.insert(table).values(values))

        # Re-link only what hasn't been given a new value in the meantime.
        for link in item.snapshot.get("links", []):
            table = _table(link["table"])
            db.execute(
                sa.update(table)
                .where(table.c.id == link["id"], table.c[link["column"]].is_(None))
                .values({link["column"]: link["value"]})
            )

        db.flush()

        for name in _files_of(rows):
            moved += _move_files([(held, live) for live, held in _file_locations(item.id, name)])

        snapshot_id = item.id
        db.delete(item)
        db.commit()
    except IntegrityError as err:
        db.rollback()
        _undo_moves(moved)
        raise HTTPException(
            status_code=409,
            detail="This can't be restored because something with the same details now exists "
            "(for example the same email address). Change that first, then try again.",
        ) from err
    except Exception:
        db.rollback()
        _undo_moves(moved)
        raise

    shutil.rmtree(_bin_dir(snapshot_id), ignore_errors=True)
    return item


def erase(db: Session, item: BinItem) -> None:
    """Permanently: the database row goes first, so a failure can't leave the bin
    listing something whose files are already gone."""
    item_id = item.id
    db.delete(item)
    db.commit()
    shutil.rmtree(_bin_dir(item_id), ignore_errors=True)


def erase_expired(db: Session) -> int:
    expired = db.query(BinItem).filter(BinItem.expires_at <= utcnow()).all()
    for item in expired:
        try:
            logged = log_type(item.item_type)
            db.add(
                AuditLog(
                    actor="system",
                    action="bin.expire",
                    entity_type=logged,
                    entity_id=item.item_id,
                    detail={"label": item.label, "note": f"Permanently deleted after {BIN_RETENTION_DAYS} days in the bin"},
                )
            )
            erase(db, item)
        except Exception:  # one bad item mustn't stop the rest
            db.rollback()
            logger.exception("Couldn't erase bin item %s", item.id)
    return len(expired)


def empty(db: Session) -> int:
    items = db.query(BinItem).all()
    for item in items:
        erase(db, item)
    return len(items)
