from sqlalchemy.orm import Session

from app.entities.document_settings import DocumentSettings

SETTINGS_ID = 1


def get_or_create_settings(db: Session) -> DocumentSettings:
    """The single settings row. Created lazily with the column defaults, so
    a fresh database (or an existing one right after this ships) renders
    documents exactly as the defaults describe, with no seeding step."""
    settings = db.get(DocumentSettings, SETTINGS_ID)
    if settings is None:
        settings = DocumentSettings(id=SETTINGS_ID)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings


def save_settings(db: Session, settings: DocumentSettings) -> DocumentSettings:
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings
