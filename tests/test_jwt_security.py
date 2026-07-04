from datetime import UTC, datetime, timedelta

import pytest
from jose import ExpiredSignatureError, JWTError, jwt

from app.core.config import get_settings
from app.core.security import create_access_token, decode_access_token


def test_create_access_token_returns_string() -> None:
    token = create_access_token("user-123")

    assert isinstance(token, str)
    assert token


def test_valid_access_token_decodes_with_expected_subject() -> None:
    token = create_access_token("user-123")

    payload = decode_access_token(token)

    assert payload["sub"] == "user-123"


def test_decoded_access_token_contains_exp_claim() -> None:
    token = create_access_token("user-123")

    payload = decode_access_token(token)

    assert "exp" in payload


def test_decode_access_token_rejects_invalid_token() -> None:
    with pytest.raises(JWTError):
        decode_access_token("not-a-valid-token")


def test_decode_access_token_rejects_expired_token() -> None:
    settings = get_settings()
    expired_token = jwt.encode(
        {
            "sub": "user-123",
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(ExpiredSignatureError):
        decode_access_token(expired_token)
