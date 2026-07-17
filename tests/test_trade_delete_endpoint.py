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
from app.models.trade import Trade


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


def register_and_login(
    client: TestClient,
    email: str = "user@example.com",
    password: str = "strongpass",
) -> tuple[str, int]:
    credentials = {"email": email, "password": password}

    register_response = client.post("/auth/register", json=credentials)
    assert register_response.status_code == 201

    login_response = client.post("/auth/login", json=credentials)
    assert login_response.status_code == 200

    return (
        login_response.json()["access_token"],
        register_response.json()["id"],
    )


def create_trade_in_db(
    client: TestClient,
    *,
    user_id: int,
    symbol: str,
    side: str,
    entry_price: str,
    exit_price: str | None,
    quantity: str,
    opened_at: datetime,
    closed_at: datetime | None,
    pnl: str | None,
    notes: str | None,
) -> Trade:
    db_generator = client.app.dependency_overrides[get_db]()
    db = next(db_generator)
    try:
        trade = Trade(
            user_id=user_id,
            symbol=symbol,
            side=side,
            entry_price=Decimal(entry_price),
            exit_price=Decimal(exit_price) if exit_price is not None else None,
            quantity=Decimal(quantity),
            opened_at=opened_at,
            closed_at=closed_at,
            pnl=Decimal(pnl) if pnl is not None else None,
            notes=notes,
        )
        db.add(trade)
        db.commit()
        db.refresh(trade)
        return trade
    finally:
        db_generator.close()


def test_delete_trade_deletes_owned_trade_and_returns_empty_204(
    client: TestClient,
) -> None:
    access_token, user_id = register_and_login(client)
    trade = create_trade_in_db(
        client,
        user_id=user_id,
        symbol="AAPL",
        side="long",
        entry_price="192.50",
        exit_price=None,
        quantity="10",
        opened_at=datetime(2026, 7, 16, 14, 0, tzinfo=UTC),
        closed_at=None,
        pnl=None,
        notes="Delete this trade.",
    )

    response = client.delete(
        f"/trades/{trade.id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 204
    assert response.content == b""

    get_response = client.get(
        f"/trades/{trade.id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert get_response.status_code == 404
    assert get_response.json() == {"detail": "Trade not found"}

    list_response = client.get(
        "/trades",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert list_response.status_code == 200
    assert list_response.json() == []


def test_delete_trade_returns_unauthorized_without_token(client: TestClient) -> None:
    response = client.delete("/trades/1")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_delete_trade_returns_unauthorized_for_invalid_token(
    client: TestClient,
) -> None:
    response = client.delete(
        "/trades/1",
        headers={"Authorization": "Bearer not-a-valid-token"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_delete_trade_returns_not_found_for_other_users_trade(
    client: TestClient,
) -> None:
    access_token, _ = register_and_login(client)
    other_access_token, other_user_id = register_and_login(
        client,
        email="other@example.com",
    )
    trade = create_trade_in_db(
        client,
        user_id=other_user_id,
        symbol="TSLA",
        side="short",
        entry_price="250.00",
        exit_price=None,
        quantity="3",
        opened_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
        closed_at=None,
        pnl=None,
        notes="Other user's trade.",
    )

    response = client.delete(
        f"/trades/{trade.id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Trade not found"}

    owner_get_response = client.get(
        f"/trades/{trade.id}",
        headers={"Authorization": f"Bearer {other_access_token}"},
    )
    assert owner_get_response.status_code == 200
    assert owner_get_response.json()["id"] == trade.id


def test_delete_trade_returns_not_found_for_missing_trade(
    client: TestClient,
) -> None:
    access_token, _ = register_and_login(client)

    response = client.delete(
        "/trades/999999",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Trade not found"}
