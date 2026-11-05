from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.auth.permissions import NOTES_ACCESS, require_permission
from app.bin.service import BinEntry, move_to_bin
from app.database import get_db
from app.datetime_utils import utcnow
from app.entities import Customer, Note
from app.errors import NotFound

from .model import NoteCreate, NoteListResponse, NoteRead, NoteStatus, NoteUpdate

router = APIRouter(prefix="/notes", tags=["Notes"])


def _customer_must_exist(db: Session, customer_id: Optional[int]) -> None:
    if customer_id is not None and not db.get(Customer, customer_id):
        raise NotFound("Customer")


def _note(db: Session, note_id: int) -> Note:
    note = db.get(Note, note_id)
    if not note:
        raise NotFound("Note")
    return note


@router.get("/", response_model=NoteListResponse)
def list_notes(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    status: Optional[NoteStatus] = None,
    db: Session = Depends(get_db),
    _user: dict = Depends(require_permission(NOTES_ACCESS)),
):
    query = db.query(Note).options(joinedload(Note.customer), joinedload(Note.invoice))
    if status:
        query = query.filter(Note.is_done.is_(status == "done"))
    total = query.count()
    # What's still to do comes first, newest on top.
    items = (
        query.order_by(Note.is_done.asc(), Note.created_at.desc(), Note.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    counts = dict(db.query(Note.is_done, func.count(Note.id)).group_by(Note.is_done).all())
    return {"items": items, "total": total, "open_count": counts.get(False, 0), "done_count": counts.get(True, 0)}


@router.post("/", response_model=NoteRead)
def create_note(payload: NoteCreate, db: Session = Depends(get_db), current_user: dict = Depends(require_permission(NOTES_ACCESS))):
    _customer_must_exist(db, payload.customer_id)
    note = Note(text=payload.text, customer_id=payload.customer_id, created_by=current_user["username"])
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@router.patch("/{note_id}", response_model=NoteRead)
def update_note(
    note_id: int,
    payload: NoteUpdate,
    db: Session = Depends(get_db),
    current_user: dict = Depends(require_permission(NOTES_ACCESS)),
):
    note = _note(db, note_id)
    fields = payload.model_fields_set

    if "text" in fields and payload.text is not None:
        note.text = payload.text
    if "customer_id" in fields:
        _customer_must_exist(db, payload.customer_id)
        note.customer_id = payload.customer_id
    if "is_done" in fields and payload.is_done is not None and payload.is_done != note.is_done:
        note.is_done = payload.is_done
        note.done_at = utcnow() if payload.is_done else None
        note.done_by = current_user["username"] if payload.is_done else None

    db.commit()
    db.refresh(note)
    return note


@router.delete("/{note_id}")
def delete_note(note_id: int, db: Session = Depends(get_db), current_user: dict = Depends(require_permission(NOTES_ACCESS))):
    note = _note(db, note_id)
    first_line = note.text.splitlines()[0] if note.text else f"Note #{note_id}"
    move_to_bin(db, [BinEntry("note", note, first_line[:120], note.customer_name)], current_user["username"])
    return {"message": "Note moved to the bin"}
