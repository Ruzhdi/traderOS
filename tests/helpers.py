from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.trade import Trade
from app.models.user import User
from app.repositories.user import create_user


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


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_user_in_db(
    db: Session,
    email: str,
    hashed_password: str = "already-hashed-password",
) -> User:
    return create_user(
        db,
        email=email,
        hashed_password=hashed_password,
    )


def create_trade_in_db(
    db: Session,
    *,
    user_id: int,
    symbol: str,
    side: str,
    entry_price: str,
    exit_price: str | None = None,
    quantity: str,
    opened_at: datetime,
    closed_at: datetime | None = None,
    pnl: str | None = None,
    notes: str | None = None,
) -> Trade:
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


def assert_datetime_equal(
    actual: str | None,
    expected: str | datetime | None,
) -> None:
    if actual is None or expected is None:
        assert actual is expected
        return

    actual_dt = datetime.fromisoformat(actual)
    expected_dt = (
        datetime.fromisoformat(expected) if isinstance(expected, str) else expected
    )

    if actual_dt.tzinfo is None:
        actual_dt = actual_dt.replace(tzinfo=UTC)
    else:
        actual_dt = actual_dt.astimezone(UTC)

    if expected_dt.tzinfo is None:
        expected_dt = expected_dt.replace(tzinfo=UTC)
    else:
        expected_dt = expected_dt.astimezone(UTC)

    assert actual_dt == expected_dt


def normalize_to_utc(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None

    dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def assert_trade_ids(response_payload: list[dict], expected_ids: list[int]) -> None:
    assert [item["id"] for item in response_payload] == expected_ids
