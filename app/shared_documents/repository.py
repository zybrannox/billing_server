import secrets
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import SHARE_LINK_EXPIRY_DAYS
from app.entities.shared_document import SharedDocument

# Its own subfolder under the same uploads root project files already use
# (see app/project_files/utils.py's UPLOAD_DIR) - a separate, unrelated
# kind of file, not a project attachment, so it gets its own namespace
# rather than mixing into that directory's flat filename space.
UPLOAD_DIR = Path("./uploads/shared_documents")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def get_by_type_and_id(db: Session, document_type: str, document_id: int) -> SharedDocument | None:
    return (
        db.query(SharedDocument)
        .filter(
            SharedDocument.document_type == document_type,
            SharedDocument.document_id == document_id,
        )
        .first()
    )


def get_by_token(db: Session, token: str) -> SharedDocument | None:
    return db.query(SharedDocument).filter(SharedDocument.token == token).first()


def _new_expiry() -> datetime:
    return datetime.utcnow() + timedelta(days=SHARE_LINK_EXPIRY_DAYS)


def get_active_by_token(db: Session, token: str) -> SharedDocument | None:
    """The link as a recipient may use it: not revoked and not expired. An
    unknown, revoked and expired token are indistinguishable to the caller on
    purpose - a probe learns nothing about which tokens ever existed."""
    doc = get_by_token(db, token)
    if doc is None or doc.revoked_at is not None:
        return None
    if doc.expires_at is not None and doc.expires_at <= datetime.utcnow():
        return None
    return doc


def revoke(db: Session, document_type: str, document_id: int) -> bool:
    """Turns the link off and deletes the stored PDF (the file is a copy of
    a financial document - no reason to keep it once nobody may fetch it).
    Sharing the document again later mints a working link again."""
    doc = get_by_type_and_id(db, document_type, document_id)
    if doc is None:
        return False
    (UPLOAD_DIR / doc.filename).unlink(missing_ok=True)
    doc.revoked_at = datetime.utcnow()
    db.commit()
    return True


def upsert(
    db: Session, document_type: str, document_id: int, file_bytes: bytes, display_name: str
) -> SharedDocument:
    """One row (and one file on disk) per document, forever reused - see
    SharedDocument's own docstring for why sharing the same invoice twice
    refreshes its existing link instead of minting a new one."""
    existing = get_by_type_and_id(db, document_type, document_id)
    if existing:
        (UPLOAD_DIR / existing.filename).write_bytes(file_bytes)
        existing.display_name = display_name
        # Re-sharing is a deliberate act: it re-opens a revoked link and
        # restarts the clock on an expiring one.
        existing.revoked_at = None
        existing.expires_at = _new_expiry()
        db.commit()
        db.refresh(existing)
        return existing

    # url-safe, 32 bytes of entropy - practically unguessable, unlike the
    # sequential invoice/quotation id this maps to.
    token = secrets.token_urlsafe(32)
    filename = f"{token}.pdf"
    (UPLOAD_DIR / filename).write_bytes(file_bytes)

    doc = SharedDocument(
        token=token,
        document_type=document_type,
        document_id=document_id,
        filename=filename,
        display_name=display_name,
        expires_at=_new_expiry(),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc
