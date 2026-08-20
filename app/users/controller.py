from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.database import get_db
from app.auth.dependencies import require_admin
from app.users import UserCreate, UserRead, UserUpdate, UserPasswordUpdate
from app.users import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/", response_model=UserRead)
async def create_user(
    user: UserCreate,
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    new_user = UserService.create_user(db, user)
    return new_user


@router.get("/", response_model=List[UserRead])
async def get_users(
    search: str | None = None,
    role: str | None = None,
    limit: int | None = None,
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    return UserService.get_all_users(db, search=search, role=role, limit=limit)


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    user = UserService.get_user_by_id(db, user_id)

    if not user:
        raise HTTPException(404, "User not found")

    return user


@router.put("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: int,
    update: UserUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    updated = UserService.update_user(db, user_id, update)

    if not updated:
        raise HTTPException(404, "User not found")

    return updated


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    success = UserService.delete_user(db, user_id)

    if not success:
        raise HTTPException(404, "User not found")

    return {"detail": "User deleted successfully"}


@router.patch("/{user_id}/password")
async def change_password(
    user_id: int,
    payload: UserPasswordUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    updated = UserService.change_password(db, user_id, payload.new_password)

    if not updated:
        raise HTTPException(404, "User not found")

    return {"detail": "Password updated successfully"}
