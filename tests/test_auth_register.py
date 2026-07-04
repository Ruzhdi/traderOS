from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

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


def test_register_user_returns_created_user(client: TestClient) -> None:
    response = client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "strongpass"},
    )

    payload = response.json()

    assert response.status_code == 201
    assert payload["id"] is not None
    assert payload["email"] == "user@example.com"
    assert payload["is_active"] is True
    assert payload["created_at"]
    assert payload["updated_at"]
    assert "password" not in payload
    assert "hashed_password" not in payload


def test_register_user_returns_conflict_for_duplicate_email(
    client: TestClient,
) -> None:
    payload = {"email": "user@example.com", "password": "strongpass"}

    first_response = client.post("/auth/register", json=payload)
    second_response = client.post("/auth/register", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409


def test_register_user_returns_validation_error_for_invalid_payload(
    client: TestClient,
) -> None:
    response = client.post(
        "/auth/register",
        json={"email": "not-an-email", "password": "short"},
    )

    assert response.status_code == 422
