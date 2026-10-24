import io
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from app.errors import BadRequest
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.project_files.service import UPLOAD_DIR
from .model import DocumentSettingsRead, DocumentSettingsUpdate
from .repository import get_or_create_settings, save_settings

BRANDING_DIR = UPLOAD_DIR / "branding"
MAX_LOGO_BYTES = 2 * 1024 * 1024
# SVG is deliberately not accepted - it can carry script, and this file is
# served back to browsers from the app's own origin.
_FORMAT_TO_EXT = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}
_EXT_TO_MEDIA = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp"}


def _to_read(settings) -> DocumentSettingsRead:
    data = DocumentSettingsRead.model_validate(settings)
    data.has_logo = bool(settings.logo_path)
    return data


def service_get(db: Session) -> DocumentSettingsRead:
    return _to_read(get_or_create_settings(db))


def service_update(db: Session, payload: DocumentSettingsUpdate) -> DocumentSettingsRead:
    settings = get_or_create_settings(db)
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("theme") == "custom" or (settings.theme == "custom" and "theme" not in changes):
        if not (changes.get("custom_color") or settings.custom_color):
            raise BadRequest("Pick a colour for the custom theme.")
    for key, value in changes.items():
        setattr(settings, key, value)
    return _to_read(save_settings(db, settings))


def _remove_logo_file(settings) -> None:
    if settings.logo_path:
        (BRANDING_DIR / settings.logo_path).unlink(missing_ok=True)


async def service_set_logo(db: Session, file: UploadFile) -> DocumentSettingsRead:
    raw = await file.read(MAX_LOGO_BYTES + 1)
    if len(raw) > MAX_LOGO_BYTES:
        raise HTTPException(status_code=413, detail="Logo must be 2 MB or smaller.")
    try:
        with Image.open(io.BytesIO(raw)) as img:
            ext = _FORMAT_TO_EXT.get(img.format or "")
            img.verify()
    except (UnidentifiedImageError, OSError):
        ext = None
    if not ext:
        raise BadRequest("Logo must be a PNG, JPEG or WebP image.")

    BRANDING_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"logo-{uuid.uuid4().hex}.{ext}"
    (BRANDING_DIR / filename).write_bytes(raw)

    settings = get_or_create_settings(db)
    old = settings.logo_path
    settings.logo_path = filename
    saved = save_settings(db, settings)
    if old:
        (BRANDING_DIR / old).unlink(missing_ok=True)
    return _to_read(saved)


def service_remove_logo(db: Session) -> DocumentSettingsRead:
    settings = get_or_create_settings(db)
    _remove_logo_file(settings)
    settings.logo_path = None
    return _to_read(save_settings(db, settings))


def service_logo_file(db: Session) -> tuple[Path, str]:
    settings = get_or_create_settings(db)
    if not settings.logo_path:
        raise HTTPException(status_code=404, detail="No custom logo set")
    path = BRANDING_DIR / settings.logo_path
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Logo file is missing")
    return path, _EXT_TO_MEDIA.get(path.suffix.lstrip("."), "application/octet-stream")
