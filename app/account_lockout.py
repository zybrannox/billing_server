"""Per-account brute-force lockout.

The per-IP rate limit on the login routes stops one machine hammering the
form, but a slow attack spread over many IPs would still get unlimited guesses
at one account. After LOGIN_MAX_FAILURES consecutive wrong passwords the
account is locked for LOGIN_LOCKOUT_MINUTES; a correct login resets the count.

The lock is short on purpose: locking is also a way for a stranger to annoy a
real user, so it expires on its own rather than needing an admin.
"""
import os

from datetime import timedelta
from typing import Protocol

from fastapi import HTTPException, status

from app.datetime_utils import utcnow

LOGIN_MAX_FAILURES = int(os.getenv("LOGIN_MAX_FAILURES", "10"))
LOGIN_LOCKOUT_MINUTES = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))


class _Lockable(Protocol):
    failed_login_count: int
    locked_until: object


def is_locked(account: _Lockable) -> bool:
    return bool(account.locked_until and account.locked_until > utcnow())


def raise_if_locked(account: _Lockable) -> None:
    if is_locked(account):
        minutes = max(1, int((account.locked_until - utcnow()).total_seconds() // 60) + 1)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed sign-in attempts. Try again in {minutes} minute{'s' if minutes != 1 else ''}.",
        )


def register_failure(account: _Lockable) -> bool:
    """Count a wrong password; returns True when this failure locked the account."""
    account.failed_login_count = (account.failed_login_count or 0) + 1
    if account.failed_login_count >= LOGIN_MAX_FAILURES:
        account.locked_until = utcnow() + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
        account.failed_login_count = 0
        return True
    return False


def register_success(account: _Lockable) -> None:
    account.failed_login_count = 0
    account.locked_until = None
