from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, hash_password
from app.models.user import User
from tests.helpers import create_user_in_db


def create_test_user(db_session: Session) -> User:
    return create_user_in_db(
        db_session,
        email="user@example.com",
        hashed_password=hash_password("strongpass"),
    )


def test_login_user_returns_access_token(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_test_user(db_session)

    response = client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "strongpass"},
    )

    payload = response.json()
    decoded_token = decode_access_token(payload["access_token"])

    assert response.status_code == 200
    assert payload["access_token"]
    assert payload["token_type"] == "bearer"
    assert decoded_token["sub"] == str(user.id)
    assert "password" not in payload
    assert "hashed_password" not in payload


def test_login_user_returns_unauthorized_for_unknown_email(
    client: TestClient,
) -> None:
    response = client.post(
        "/auth/login",
        json={"email": "missing@example.com", "password": "strongpass"},
    )

    assert response.status_code == 401


def test_login_user_returns_unauthorized_for_wrong_password(
    client: TestClient,
    db_session: Session,
) -> None:
    create_test_user(db_session)

    response = client.post(
        "/auth/login",
        json={"email": "user@example.com", "password": "wrongpass"},
    )

    assert response.status_code == 401


def test_login_user_returns_validation_error_for_invalid_payload(
    client: TestClient,
) -> None:
    response = client.post(
        "/auth/login",
        json={"email": "not-an-email", "password": "short"},
    )

    assert response.status_code == 422
