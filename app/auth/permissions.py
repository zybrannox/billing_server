"""What an admin can grant to individual employees.

Admins can always do everything. Everyone else starts with none of these, and
each is enforced here on the server: hiding a button is only a convenience.
"""
from fastapi import Depends, HTTPException

from .dependencies import get_current_user

INVOICE_CREATE = "invoice.create"
INVOICE_EDIT = "invoice.edit"
WORKSPACE_MANAGE = "workspace.manage"
NOTES_ACCESS = "notes.access"

PERMISSION_LABELS = {
    INVOICE_CREATE: "New invoices",
    INVOICE_EDIT: "Edit invoices",
    WORKSPACE_MANAGE: "Workspace settings",
    NOTES_ACCESS: "Notes",
}
ALL_PERMISSIONS = tuple(PERMISSION_LABELS)

_DENIED = {
    INVOICE_CREATE: "You don't have access to create invoices. Ask an admin to give you access.",
    INVOICE_EDIT: "You don't have access to edit invoices. Ask an admin to give you access.",
    WORKSPACE_MANAGE: "You don't have access to workspace settings. Ask an admin to give you access.",
    NOTES_ACCESS: "You don't have access to notes. Ask an admin to give you access.",
}


def has_permission(current_user: dict, permission: str) -> bool:
    return permission in current_user.get("permissions", [])


def can_see_invoices(current_user: dict) -> bool:
    """Reading the full invoice list goes with being trusted to make or edit them."""
    return has_permission(current_user, INVOICE_CREATE) or has_permission(current_user, INVOICE_EDIT)


def require_invoice_access(current_user: dict = Depends(get_current_user)) -> dict:
    if not can_see_invoices(current_user):
        raise HTTPException(status_code=403, detail="You don't have access to invoices. Ask an admin to give you access.")
    return current_user


def require_permission(permission: str):
    def check(current_user: dict = Depends(get_current_user)) -> dict:
        if not has_permission(current_user, permission):
            raise HTTPException(status_code=403, detail=_DENIED[permission])
        return current_user

    return check
