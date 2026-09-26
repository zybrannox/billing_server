import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session
from sqlalchemy import select
from passlib.hash import bcrypt
from fastapi import HTTPException, status

from app.entities import ClientAccount, Customer, Company
from app.security import create_client_access_token
from app.email_service import generate_verification_code, send_password_reset_code

INVITE_EXPIRY_DAYS = 7
RESET_CODE_EXPIRY_MINUTES = 15


class ClientAuthService:
    # Same constant-time-lookup trick as AuthService._DUMMY_HASH (see
    # app/auth/service.py) - verified against on every login for an email
    # that doesn't exist, so "no such account" and "wrong password" take
    # the same ~100ms and can't be told apart by timing.
    _DUMMY_HASH = bcrypt.hash("not-a-real-password")

    @staticmethod
    def create_invite(db: Session, customer_id: int, invited_by: str) -> ClientAccount:
        customer = db.get(Customer, customer_id)
        if not customer:
            raise HTTPException(status_code=404, detail="Customer not found")

        account = db.execute(
            select(ClientAccount).where(ClientAccount.customer_id == customer_id)
        ).scalar_one_or_none()

        if account and account.activated_at is not None:
            raise HTTPException(
                status_code=400,
                detail="This customer already has an active portal account.",
            )

        token = secrets.token_urlsafe(32)
        expires_at = datetime.utcnow() + timedelta(days=INVITE_EXPIRY_DAYS)

        if account:
            # Resend - refresh the token rather than minting a second row.
            account.invite_token = token
            account.invite_token_expires_at = expires_at
            account.invited_at = datetime.utcnow()
            account.invited_by = invited_by
        else:
            account = ClientAccount(
                customer_id=customer_id,
                invite_token=token,
                invite_token_expires_at=expires_at,
                invited_at=datetime.utcnow(),
                invited_by=invited_by,
            )
            db.add(account)

        db.commit()
        db.refresh(account)
        return account

    @staticmethod
    def get_invite(db: Session, token: str):
        account = db.execute(
            select(ClientAccount).where(ClientAccount.invite_token == token)
        ).scalar_one_or_none()

        if not account or not account.invite_token_expires_at or account.invite_token_expires_at < datetime.utcnow():
            return None

        customer = db.get(Customer, account.customer_id)
        company = db.get(Company, customer.company_id) if customer and customer.company_id else None
        return customer, company

    @staticmethod
    def activate_account(db: Session, token: str, email: str, password: str) -> ClientAccount:
        account = db.execute(
            select(ClientAccount).where(ClientAccount.invite_token == token)
        ).scalar_one_or_none()

        if not account or not account.invite_token_expires_at or account.invite_token_expires_at < datetime.utcnow():
            raise HTTPException(status_code=400, detail="This invite link is invalid or has expired.")

        existing_email = db.execute(
            select(ClientAccount).where(
                ClientAccount.email == email, ClientAccount.id != account.id
            )
        ).scalar_one_or_none()
        if existing_email:
            raise HTTPException(status_code=400, detail="This email is already registered to a portal account.")

        account.email = email
        account.hashed_password = bcrypt.hash(password)
        account.activated_at = datetime.utcnow()
        # Single-use - a leaked activation link can't be replayed once used.
        account.invite_token = None
        account.invite_token_expires_at = None

        db.commit()
        db.refresh(account)
        return account

    @staticmethod
    def authenticate_client(db: Session, email: str, password: str) -> str:
        account = db.execute(
            select(ClientAccount).where(ClientAccount.email == email)
        ).scalar_one_or_none()

        password_hash = account.hashed_password if account and account.hashed_password else ClientAuthService._DUMMY_HASH
        password_ok = bcrypt.verify(password, password_hash)

        if not account or not password_ok:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        if not account.is_active or account.activated_at is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive")

        return create_client_access_token({"sub": str(account.id)})

    # Same shape as AuthService.request_password_reset (app/auth/
    # service.py) - one fixed outcome regardless of whether the email
    # matches a real, activated account. An account that was invited but
    # never activated (no password set yet) also gets nothing here - it
    # has nothing to reset; the invite link is what sets its first
    # password.
    @staticmethod
    def request_password_reset(db: Session, email: str) -> None:
        account = db.execute(
            select(ClientAccount).where(ClientAccount.email == email)
        ).scalar_one_or_none()
        if not account or not account.is_active or account.activated_at is None:
            return

        code = generate_verification_code()
        account.reset_code = code
        account.reset_code_expires_at = datetime.utcnow() + timedelta(minutes=RESET_CODE_EXPIRY_MINUTES)
        db.commit()

        send_password_reset_code(account.email, code)

    @staticmethod
    def reset_password(db: Session, email: str, code: str, new_password: str) -> None:
        account = db.execute(
            select(ClientAccount).where(ClientAccount.email == email)
        ).scalar_one_or_none()

        valid = (
            account is not None
            and account.reset_code is not None
            and account.reset_code == code
            and account.reset_code_expires_at is not None
            and account.reset_code_expires_at >= datetime.utcnow()
        )
        if not valid:
            raise HTTPException(status_code=400, detail="Invalid or expired verification code.")

        account.hashed_password = bcrypt.hash(new_password)
        account.reset_code = None
        account.reset_code_expires_at = None
        db.commit()
