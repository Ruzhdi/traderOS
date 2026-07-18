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


def test_list_trades_returns_only_current_users_trades(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, user_id = register_and_login(client)
    other_user = create_user_in_db(db_session, "other@example.com")

    newer_trade = create_trade_in_db(
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
    older_trade = create_trade_in_db(
        db_session,
        user_id=user_id,
        symbol="MSFT",
        side="short",
        entry_price="430.00",
        exit_price=None,
        quantity="2.5",
        opened_at=datetime(2026, 7, 15, 13, 30, tzinfo=UTC),
        closed_at=None,
        pnl=None,
        notes=None,
    )
    create_trade_in_db(
        db_session,
        user_id=other_user.id,
        symbol="TSLA",
        side="long",
        entry_price="250.00",
        exit_price="255.00",
        quantity="5",
        opened_at=datetime(2026, 7, 16, 9, 30, tzinfo=UTC),
        closed_at=datetime(2026, 7, 16, 10, 15, tzinfo=UTC),
        pnl="25.00",
        notes="Should not be returned.",
    )

    response = client.get(
        "/trades",
        headers=auth_headers(access_token),
    )

    response_payload = response.json()

    assert response.status_code == 200
    assert isinstance(response_payload, list)
    assert len(response_payload) == 2
    assert [item["id"] for item in response_payload] == [newer_trade.id, older_trade.id]
    assert {item["user_id"] for item in response_payload} == {user_id}
    assert {item["symbol"] for item in response_payload} == {"AAPL", "MSFT"}
    assert all(item["symbol"] != "TSLA" for item in response_payload)

    first_item = response_payload[0]
    assert set(first_item) == {
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
    assert first_item["id"] == newer_trade.id
    assert first_item["user_id"] == user_id
    assert first_item["symbol"] == "AAPL"
    assert first_item["side"] == "long"
    assert Decimal(first_item["entry_price"]) == Decimal("192.50")
    assert Decimal(first_item["exit_price"]) == Decimal("198.75")
    assert Decimal(first_item["quantity"]) == Decimal("10")
    assert Decimal(first_item["pnl"]) == Decimal("62.50")
    assert first_item["notes"] == "Earnings continuation breakout."
    assert_datetime_equal(first_item["opened_at"], newer_trade.opened_at)
    assert_datetime_equal(first_item["closed_at"], newer_trade.closed_at)
    assert first_item["created_at"]
    assert first_item["updated_at"]

    second_item = response_payload[1]
    assert second_item["id"] == older_trade.id
    assert second_item["user_id"] == user_id
    assert second_item["symbol"] == "MSFT"
    assert second_item["side"] == "short"
    assert Decimal(second_item["entry_price"]) == Decimal("430.00")
    assert second_item["exit_price"] is None
    assert Decimal(second_item["quantity"]) == Decimal("2.5")
    assert second_item["closed_at"] is None
    assert second_item["pnl"] is None
    assert second_item["notes"] is None
    assert_datetime_equal(second_item["opened_at"], older_trade.opened_at)
    assert second_item["created_at"]
    assert second_item["updated_at"]


def test_list_trades_returns_empty_list_when_user_has_no_trades(
    client: TestClient,
) -> None:
    access_token, _ = register_and_login(client)

    response = client.get(
        "/trades",
        headers=auth_headers(access_token),
    )

    assert response.status_code == 200
    assert response.json() == []


def test_list_trades_returns_unauthorized_without_token(client: TestClient) -> None:
    response = client.get("/trades")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_list_trades_returns_unauthorized_for_invalid_token(
    client: TestClient,
) -> None:
    response = client.get(
        "/trades",
        headers=auth_headers("not-a-valid-token"),
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
