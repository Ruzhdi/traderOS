from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.user import User
from app.schemas.user import UserCreate, UserRead


def test_user_create_accepts_valid_data() -> None:
    schema = UserCreate(email="user@example.com", password="strongpass")

    assert schema.email == "user@example.com"
    assert schema.password == "strongpass"


def test_user_create_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError):
        UserCreate(email="not-an-email", password="strongpass")


def test_user_create_rejects_short_password() -> None:
    with pytest.raises(ValidationError):
        UserCreate(email="user@example.com", password="short")


def test_user_read_omits_hashed_password_from_dump() -> None:
    now = datetime.now(UTC)
    user = User(
        id=1,
        email="user@example.com",
        hashed_password="hashed-secret",
        is_active=True,
        created_at=now,
        updated_at=now,
    )

    schema = UserRead.model_validate(user)
    payload = schema.model_dump()

    assert payload == {
        "id": 1,
        "email": "user@example.com",
        "is_active": True,
        "created_at": now,
        "updated_at": now,
    }
    assert "hashed_password" not in payload
