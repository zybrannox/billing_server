"""One password rule for every place a new password is set (admin creating a
user, changing a password, forgot-password reset, client-portal activation).
Applied to new passwords only - existing ones keep working until changed.

Follows current NIST SP 800-63B guidance: length matters more than character
gymnastics, so there's a generous minimum and a block on trivially guessable
choices, but no "must contain a symbol" rule."""
from typing import Annotated

from pydantic import AfterValidator

MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 128  # bcrypt only uses the first 72 bytes; also caps hashing cost

# The passwords people actually pick, padded out past the length minimum.
_COMMON = {
    "password1", "password12", "password123", "password1234", "passw0rd123",
    "1234567890", "12345678910", "0123456789", "qwertyuiop", "qwerty12345",
    "iloveyou123", "admin12345", "administrator", "welcome123", "welcome1234",
    "letmein1234", "zybrannox", "zybrannox123", "changeme123",
}


def validate_password_strength(value: str) -> str:
    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long.")
    if len(value) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters long.")
    if len(set(value)) < 4:
        raise ValueError("Password is too repetitive - use a longer, more varied one.")
    if value.lower() in _COMMON:
        raise ValueError("That password is too common - choose something less guessable.")
    return value


# Drop-in field type: `new_password: StrongPassword`.
StrongPassword = Annotated[str, AfterValidator(validate_password_strength)]
