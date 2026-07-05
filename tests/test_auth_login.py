from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import decode_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.user import User


@pytest.fixture
def client() -> Generator[TestClient]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    assert User.__tablename__ == "users"
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def create_test_user() -> User:
    db_generator = app.dependency_overrides[get_db]()
    db = next(db_generator)
    try:
        user = User(
            email="user@example.com",
            hashed_password=hash_password("strongpass"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db_generator.close()


def test_login_user_returns_access_token(client: TestClient) -> None:
    user = create_test_user()

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
) -> None:
    create_test_user()

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
