from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app


@pytest.fixture
def client() -> Generator[TestClient]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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


def register_and_login(client: TestClient) -> tuple[str, int]:
    credentials = {"email": "user@example.com", "password": "strongpass"}

    register_response = client.post("/auth/register", json=credentials)
    assert register_response.status_code == 201

    login_response = client.post("/auth/login", json=credentials)
    assert login_response.status_code == 200

    return (
        login_response.json()["access_token"],
        register_response.json()["id"],
    )


def assert_datetime_equal(actual: str, expected: str) -> None:
    actual_dt = datetime.fromisoformat(actual)
    expected_dt = datetime.fromisoformat(expected)

    if actual_dt.tzinfo is None:
        actual_dt = actual_dt.replace(tzinfo=UTC)

    if expected_dt.tzinfo is None:
        expected_dt = expected_dt.replace(tzinfo=UTC)

    assert actual_dt == expected_dt


def test_create_trade_returns_created_trade_for_authenticated_user(
    client: TestClient,
) -> None:
    access_token, user_id = register_and_login(client)
    payload = {
        "symbol": "AAPL",
        "side": "long",
        "entry_price": "192.50",
        "exit_price": "198.75",
        "quantity": "10",
        "opened_at": datetime(2026, 7, 16, 9, 30, tzinfo=UTC).isoformat(),
        "closed_at": datetime(2026, 7, 16, 15, 45, tzinfo=UTC).isoformat(),
        "pnl": "62.50",
        "notes": "Earnings continuation breakout.",
    }

    response = client.post(
        "/trades",
        json=payload,
        headers={"Authorization": f"Bearer {access_token}"},
    )

    response_payload = response.json()

    assert response.status_code == 201
    assert set(response_payload) == {
        "id",
        "user_id",
        "symbol",
        "side",
        "entry_price",
        "exit_price",
        "quantity",
        "opened_at",
        "closed_at",
        "pnl",
        "notes",
        "created_at",
        "updated_at",
    }
    assert response_payload["id"] is not None
    assert response_payload["user_id"] == user_id
    assert response_payload["symbol"] == payload["symbol"]
    assert response_payload["side"] == payload["side"]
    assert Decimal(response_payload["entry_price"]) == Decimal(payload["entry_price"])
    assert Decimal(response_payload["exit_price"]) == Decimal(payload["exit_price"])
    assert Decimal(response_payload["quantity"]) == Decimal(payload["quantity"])
    assert Decimal(response_payload["pnl"]) == Decimal(payload["pnl"])
    assert_datetime_equal(response_payload["opened_at"], payload["opened_at"])
    assert_datetime_equal(response_payload["closed_at"], payload["closed_at"])
    assert response_payload["notes"] == payload["notes"]
    assert response_payload["created_at"]
    assert response_payload["updated_at"]


def test_create_trade_returns_unauthorized_without_token(client: TestClient) -> None:
    response = client.post(
        "/trades",
        json={
            "symbol": "AAPL",
            "side": "long",
            "entry_price": "192.50",
            "quantity": "10",
            "opened_at": datetime(2026, 7, 16, 9, 30, tzinfo=UTC).isoformat(),
        },
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_create_trade_returns_unauthorized_for_invalid_token(
    client: TestClient,
) -> None:
    response = client.post(
        "/trades",
        json={
            "symbol": "AAPL",
            "side": "long",
            "entry_price": "192.50",
            "quantity": "10",
            "opened_at": datetime(2026, 7, 16, 9, 30, tzinfo=UTC).isoformat(),
        },
        headers={"Authorization": "Bearer not-a-valid-token"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_create_trade_returns_validation_error_for_invalid_body(
    client: TestClient,
) -> None:
    access_token, _ = register_and_login(client)

    response = client.post(
        "/trades",
        json={
            "symbol": "",
            "side": "buy",
            "entry_price": "0",
            "quantity": "-1",
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 422


def test_create_trade_ignores_user_id_from_request_body(client: TestClient) -> None:
    access_token, user_id = register_and_login(client)

    response = client.post(
        "/trades",
        json={
            "user_id": 999999,
            "symbol": "TSLA",
            "side": "short",
            "entry_price": "250.00",
            "exit_price": None,
            "quantity": "3",
            "opened_at": datetime(2026, 7, 16, 10, 0, tzinfo=UTC).isoformat(),
            "closed_at": None,
            "pnl": None,
            "notes": "Opening position.",
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )

    response_payload = response.json()

    assert response.status_code == 201
    assert response_payload["user_id"] == user_id
    assert response_payload["user_id"] != 999999
