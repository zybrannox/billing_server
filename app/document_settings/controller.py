from fastapi import APIRouter, Cookie, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.auth.dependencies import get_current_user, require_admin
from app.client_auth.dependencies import get_current_client
from .model import DocumentSettingsRead, DocumentSettingsUpdate
from .service import (
    service_get,
    service_update,
    service_set_logo,
    service_remove_logo,
    service_logo_file,
)

router = APIRouter(prefix="/document-settings", tags=["Document Settings"])


def staff_or_client(
    access_token: str = Cookie(None),
    client_access_token: str = Cookie(None),
    db: Session = Depends(get_db),
) -> dict:
    """Read access for anyone who can see a printed document: staff, and
    portal clients (the client portal renders the same invoice sheet - see
    portal/pages/PortalInvoiceDetail.tsx). Each token is still validated by
    its own dependency, so the two auth boundaries stay separate."""
    if access_token:
        try:
            return get_current_user(access_token, db)
        except HTTPException:
            pass
    if client_access_token:
        try:
            return get_current_client(client_access_token, db)
        except HTTPException:
            pass
    raise HTTPException(status_code=401, detail="Not authenticated")


@router.get("/", response_model=DocumentSettingsRead)
def get_settings(db: Session = Depends(get_db), _user: dict = Depends(staff_or_client)):
    return service_get(db)


@router.put("/", response_model=DocumentSettingsRead)
def update_settings(
    payload: DocumentSettingsUpdate,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    return service_update(db, payload)


@router.get("/logo")
def get_logo(db: Session = Depends(get_db), _user: dict = Depends(staff_or_client)):
    path, media_type = service_logo_file(db)
    # The filename is unique per upload, so a changed logo is a new file the
    # settings payload points the client at - safe to let it cache briefly.
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "private, max-age=300"})


@router.post("/logo", response_model=DocumentSettingsRead)
async def upload_logo(
    file: UploadFile,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    return await service_set_logo(db, file)


@router.delete("/logo", response_model=DocumentSettingsRead)
def delete_logo(db: Session = Depends(get_db), _admin: dict = Depends(require_admin)):
    return service_remove_logo(db)
