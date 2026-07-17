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
from app.models.user import User
from app.repositories.user import create_user


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


def create_user_in_db(client: TestClient, email: str) -> User:
    db_generator = client.app.dependency_overrides[get_db]()
    db = next(db_generator)
    try:
        return create_user(
            db,
            email=email,
            hashed_password="already-hashed-password",
        )
    finally:
        db_generator.close()


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


def normalize_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def assert_datetime_equal(actual: str | None, expected: datetime | None) -> None:
    if actual is None or expected is None:
        assert actual is expected
        return

    actual_dt = normalize_utc(datetime.fromisoformat(actual))
    expected_dt = normalize_utc(expected)
    assert actual_dt == expected_dt


def test_update_trade_updates_one_field_for_authenticated_owner(
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
        notes="Initial note.",
    )

    response = client.patch(
        f"/trades/{trade.id}",
        json={"notes": "Updated note."},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    response_payload = response.json()

    assert response.status_code == 200
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
    assert response_payload["id"] == trade.id
    assert response_payload["user_id"] == user_id
    assert response_payload["symbol"] == "AAPL"
    assert response_payload["side"] == "long"
    assert Decimal(response_payload["entry_price"]) == Decimal("192.50")
    assert response_payload["exit_price"] is None
    assert Decimal(response_payload["quantity"]) == Decimal("10")
    assert response_payload["closed_at"] is None
    assert response_payload["pnl"] is None
    assert response_payload["notes"] == "Updated note."
    assert_datetime_equal(response_payload["opened_at"], trade.opened_at)
    assert response_payload["created_at"]
    assert response_payload["updated_at"]


def test_update_trade_updates_multiple_fields_for_authenticated_owner(
    client: TestClient,
) -> None:
    access_token, user_id = register_and_login(client)
    trade = create_trade_in_db(
        client,
        user_id=user_id,
        symbol="TSLA",
        side="short",
        entry_price="250.00",
        exit_price=None,
        quantity="3",
        opened_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
        closed_at=None,
        pnl=None,
        notes="Opening position.",
    )
    closed_at = datetime(2026, 7, 16, 14, 45, tzinfo=UTC)

    response = client.patch(
        f"/trades/{trade.id}",
        json={
            "exit_price": "241.25",
            "closed_at": closed_at.isoformat(),
            "pnl": "26.25",
            "notes": "Covered into weakness.",
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )

    response_payload = response.json()

    assert response.status_code == 200
    assert response_payload["id"] == trade.id
    assert response_payload["user_id"] == user_id
    assert response_payload["symbol"] == "TSLA"
    assert response_payload["side"] == "short"
    assert Decimal(response_payload["entry_price"]) == Decimal("250.00")
    assert Decimal(response_payload["exit_price"]) == Decimal("241.25")
    assert Decimal(response_payload["quantity"]) == Decimal("3")
    assert Decimal(response_payload["pnl"]) == Decimal("26.25")
    assert response_payload["notes"] == "Covered into weakness."
    assert_datetime_equal(response_payload["opened_at"], trade.opened_at)
    assert_datetime_equal(response_payload["closed_at"], closed_at)
    assert response_payload["created_at"]
    assert response_payload["updated_at"]


def test_update_trade_does_not_overwrite_missing_fields_with_null(
    client: TestClient,
) -> None:
    access_token, user_id = register_and_login(client)
    original_closed_at = datetime(2026, 7, 16, 15, 0, tzinfo=UTC)
    trade = create_trade_in_db(
        client,
        user_id=user_id,
        symbol="NVDA",
        side="long",
        entry_price="130.00",
        exit_price="134.50",
        quantity="4",
        opened_at=datetime(2026, 7, 16, 13, 15, tzinfo=UTC),
        closed_at=original_closed_at,
        pnl="18.00",
        notes="Original note.",
    )

    response = client.patch(
        f"/trades/{trade.id}",
        json={"symbol": "NVDA-W1", "notes": "Updated note."},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    response_payload = response.json()

    assert response.status_code == 200
    assert response_payload["symbol"] == "NVDA-W1"
    assert response_payload["notes"] == "Updated note."
    assert Decimal(response_payload["exit_price"]) == Decimal("134.50")
    assert Decimal(response_payload["pnl"]) == Decimal("18.00")
    assert_datetime_equal(response_payload["closed_at"], original_closed_at)


def test_update_trade_returns_unauthorized_without_token(
    client: TestClient,
) -> None:
    response = client.patch("/trades/1", json={"notes": "Updated note."})

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_update_trade_returns_unauthorized_for_invalid_token(
    client: TestClient,
) -> None:
    response = client.patch(
        "/trades/1",
        json={"notes": "Updated note."},
        headers={"Authorization": "Bearer not-a-valid-token"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_update_trade_returns_not_found_for_other_users_trade(
    client: TestClient,
) -> None:
    access_token, _ = register_and_login(client)
    other_user = create_user_in_db(client, "other@example.com")
    trade = create_trade_in_db(
        client,
        user_id=other_user.id,
        symbol="MSFT",
        side="long",
        entry_price="430.00",
        exit_price="435.50",
        quantity="2",
        opened_at=datetime(2026, 7, 16, 11, 0, tzinfo=UTC),
        closed_at=datetime(2026, 7, 16, 15, 30, tzinfo=UTC),
        pnl="11.00",
        notes="Owner trade.",
    )

    response = client.patch(
        f"/trades/{trade.id}",
        json={"notes": "Not allowed.", "exit_price": "999.99"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Trade not found"}


def test_update_trade_returns_not_found_for_missing_trade(
    client: TestClient,
) -> None:
    access_token, _ = register_and_login(client)

    response = client.patch(
        "/trades/999999",
        json={"notes": "Missing trade."},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Trade not found"}


def test_update_trade_returns_validation_error_for_invalid_body(
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
        notes="Initial note.",
    )

    response = client.patch(
        f"/trades/{trade.id}",
        json={"symbol": "", "side": "buy", "entry_price": "0", "quantity": "-1"},
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 422
