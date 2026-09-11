from sqlalchemy.orm import Session
from sqlalchemy import select, or_
from passlib.hash import bcrypt
from app.entities import User, UserRole
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
from app.projects.repository import get_all_projects
from app.users.model import EmployeeStats, EmployeeProfile


class UserService:

    @staticmethod
    def create_user(db: Session, user):

        # check phone exists
        exists = db.execute(
            select(User).where(User.phone == user.phone)
        ).scalar_one_or_none()

        if exists:
            raise HTTPException(status_code=400, detail="Phone already registered")

        # check email exists
        exists = db.execute(
            select(User).where(User.email == user.email)
        ).scalar_one_or_none()

        if exists:
            raise HTTPException(status_code=400, detail="Email already registered")

        hashed_password = bcrypt.hash(user.password)

        new_user = User(
            username=user.username,
            email=user.email,
            phone=user.phone,
            hashed_password=hashed_password,
            role=user.role,
            is_active=user.is_active,
        )

        try:
            db.add(new_user)
            db.commit()
            db.refresh(new_user)

        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=400, detail="Duplicate user data")

        return new_user

    @staticmethod
    def get_all_users(
        db: Session,
        search: str | None = None,
        role: str | None = None,
        limit: int | None = None,
    ):
        # search/role/limit are all optional and unbounded by default, so the
        # full Employee Details table keeps working unchanged; callers that
        # want a fast, capped lookup (e.g. an "Assigned To" search dropdown)
        # opt in explicitly.
        query = select(User)

        if search:
            like = f"%{search}%"
            query = query.where(
                or_(User.username.ilike(like), User.email.ilike(like))
            )

        if role:
            try:
                query = query.where(User.role == UserRole(role))
            except ValueError:
                return []

        query = query.order_by(User.username)

        if limit:
            query = query.limit(limit)

        return db.execute(query).scalars().all()

    @staticmethod
    def get_user_by_id(db: Session, user_id: int):
        return db.execute(
            select(User).where(User.id == user_id)
        ).scalar_one_or_none()

    # One call for the whole profile page (see EmployeeProfile) - identity,
    # every project assigned to this employee, and the summary numbers -
    # instead of the frontend firing separate requests. Matched by username
    # since that's the only link Project.assigned_to actually stores (see
    # EmployeeStats' docstring); page_size is generous rather than paginated
    # for the same reason as CustomerService.get_customer_profile - one
    # employee's own work history is small enough to show in full here.
    @staticmethod
    def get_employee_profile(db: Session, user_id: int) -> EmployeeProfile | None:
        user = UserService.get_user_by_id(db, user_id)
        if not user:
            return None

        projects, _ = get_all_projects(db, page=1, page_size=500, assigned_to=user.username)

        active_assigned = sum(1 for p in projects if p.delivered_at is None)
        designs_completed = sum(1 for p in projects if p.design_completed_by == user.username)
        prints_completed = sum(1 for p in projects if p.print_completed_by == user.username)
        deliveries_completed = sum(1 for p in projects if p.delivered_by == user.username)

        return EmployeeProfile(
            user=user,
            stats=EmployeeStats(
                total_assigned=len(projects),
                active_assigned=active_assigned,
                designs_completed=designs_completed,
                prints_completed=prints_completed,
                deliveries_completed=deliveries_completed,
            ),
            projects=projects,
        )

    @staticmethod
    def update_user(db: Session, user_id: int, update):
        user = UserService.get_user_by_id(db, user_id)
        if not user:
            return None

        update_data = update.model_dump(exclude_unset=True)

        # Uniqueness checks only for fields that are actually changing -
        # same guard as create_user, just scoped to "changed" so saving a
        # row without touching phone/email doesn't false-positive on itself.
        if "phone" in update_data and update_data["phone"] != user.phone:
            exists = db.execute(
                select(User).where(User.phone == update_data["phone"])
            ).scalar_one_or_none()
            if exists:
                raise HTTPException(status_code=400, detail="Phone already registered")

        if "email" in update_data and update_data["email"] != user.email:
            exists = db.execute(
                select(User).where(User.email == update_data["email"])
            ).scalar_one_or_none()
            if exists:
                raise HTTPException(status_code=400, detail="Email already registered")

        for key, value in update_data.items():
            setattr(user, key, value)

        try:
            db.commit()
            db.refresh(user)
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=400, detail="Duplicate user data")

        return user

    @staticmethod
    def delete_user(db: Session, user_id: int):
        user = UserService.get_user_by_id(db, user_id)
        if not user:
            return False

        db.delete(user)
        db.commit()
        return True

    @staticmethod
    def change_password(db: Session, user_id: int, new_password: str):
        user = UserService.get_user_by_id(db, user_id)
        if not user:
            return None

        user.hashed_password = bcrypt.hash(new_password)
        db.commit()
        db.refresh(user)
        return user
