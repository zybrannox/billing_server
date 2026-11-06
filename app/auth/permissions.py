"""What an admin can grant to individual employees.

Admins can always do everything. Everyone else starts with none of these, and
each is enforced here on the server: hiding a button is only a convenience.
"""
from fastapi import Depends, HTTPException

from .dependencies import get_current_user

INVOICE_EDIT = "invoice.edit"
WORKSPACE_MANAGE = "workspace.manage"
NOTES_ACCESS = "notes.access"

PERMISSION_LABELS = {
    INVOICE_EDIT: "Edit project invoices",
    WORKSPACE_MANAGE: "Workspace settings",
    NOTES_ACCESS: "Notes",
}
ALL_PERMISSIONS = tuple(PERMISSION_LABELS)

_DENIED = {
    INVOICE_EDIT: "You don't have access to edit invoices. Ask an admin to give you access.",
    WORKSPACE_MANAGE: "You don't have access to workspace settings. Ask an admin to give you access.",
    NOTES_ACCESS: "You don't have access to notes. Ask an admin to give you access.",
}


def has_permission(current_user: dict, permission: str) -> bool:
    return permission in current_user.get("permissions", [])


def require_permission(permission: str):
    def check(current_user: dict = Depends(get_current_user)) -> dict:
        if not has_permission(current_user, permission):
            raise HTTPException(status_code=403, detail=_DENIED[permission])
        return current_user

    return check
