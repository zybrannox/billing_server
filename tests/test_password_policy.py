import pytest
from pydantic import ValidationError

from app.password_policy import MIN_PASSWORD_LENGTH, validate_password_strength
from app.users.model import UserPasswordUpdate


@pytest.mark.parametrize("good", ["correct horse battery", "a-Long-enough-1", "aabbccdd1122"])
def test_accepts_reasonable_passwords(good):
    assert validate_password_strength(good) == good


@pytest.mark.parametrize(
    "bad",
    ["short", "a" * 9, "aaaaaaaaaaaa", "1111111111", "Password123", "ZYBRANNOX123", "x" * 200],
)
def test_rejects_weak_or_invalid_passwords(bad):
    with pytest.raises(ValueError):
        validate_password_strength(bad)


def test_minimum_is_ten():
    assert MIN_PASSWORD_LENGTH == 10


def test_applied_to_request_models():
    with pytest.raises(ValidationError):
        UserPasswordUpdate(new_password="short1")
    assert UserPasswordUpdate(new_password="a perfectly fine phrase").new_password
