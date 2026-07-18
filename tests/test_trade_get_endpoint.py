from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.helpers import (
    assert_datetime_equal,
    auth_headers,
    create_trade_in_db,
    create_user_in_db,
    register_and_login,
)


def test_get_trade_by_id_returns_owned_trade_for_authenticated_user(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, user_id = register_and_login(client)
    trade = create_trade_in_db(
        db_session,
        user_id=user_id,
        symbol="AAPL",
        side="long",
        entry_price="192.50",
        exit_price="198.75",
        quantity="10",
        opened_at=datetime(2026, 7, 16, 14, 0, tzinfo=UTC),
        closed_at=datetime(2026, 7, 16, 15, 45, tzinfo=UTC),
        pnl="62.50",
        notes="Earnings continuation breakout.",
    )

    response = client.get(
        f"/trades/{trade.id}",
        headers=auth_headers(access_token),
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
    assert Decimal(response_payload["exit_price"]) == Decimal("198.75")
    assert Decimal(response_payload["quantity"]) == Decimal("10")
    assert Decimal(response_payload["pnl"]) == Decimal("62.50")
    assert response_payload["notes"] == "Earnings continuation breakout."
    assert_datetime_equal(response_payload["opened_at"], trade.opened_at)
    assert_datetime_equal(response_payload["closed_at"], trade.closed_at)
    assert response_payload["created_at"]
    assert response_payload["updated_at"]


def test_get_trade_by_id_returns_unauthorized_without_token(
    client: TestClient,
) -> None:
    response = client.get("/trades/1")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_get_trade_by_id_returns_unauthorized_for_invalid_token(
    client: TestClient,
) -> None:
    response = client.get(
        "/trades/1",
        headers=auth_headers("not-a-valid-token"),
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_get_trade_by_id_returns_not_found_for_other_users_trade(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, _ = register_and_login(client)
    other_user = create_user_in_db(db_session, "other@example.com")
    trade = create_trade_in_db(
        db_session,
        user_id=other_user.id,
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

    response = client.get(
        f"/trades/{trade.id}",
        headers=auth_headers(access_token),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Trade not found"}


def test_get_trade_by_id_returns_not_found_for_missing_trade(
    client: TestClient,
) -> None:
    access_token, _ = register_and_login(client)

    response = client.get(
        "/trades/999999",
        headers=auth_headers(access_token),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Trade not found"}
