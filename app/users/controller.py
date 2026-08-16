from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.database import get_db
from app.users import UserCreate, UserRead, UserUpdate
from app.users import UserService

router = APIRouter(prefix="/users", tags=["Users"])


@router.post("/", response_model=UserRead)
async def create_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
    new_user = UserService.create_user(db, user)
    return new_user


@router.get("/", response_model=List[UserRead])
async def get_users(db: AsyncSession = Depends(get_db)):
    return UserService.get_all_users(db)


@router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    user = UserService.get_user_by_id(db, user_id)

    if not user:
        raise HTTPException(404, "User not found")

    return user


@router.put("/{user_id}", response_model=UserRead)
async def update_user(user_id: int, update: UserUpdate, db: AsyncSession = Depends(get_db)):
    updated = UserService.update_user(db, user_id, update)

    if not updated:
        raise HTTPException(404, "User not found")

    return updated


@router.delete("/{user_id}")
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db)):
    success = UserService.delete_user(db, user_id)

    if not success:
        raise HTTPException(404, "User not found")

    return {"detail": "User deleted successfully"}
