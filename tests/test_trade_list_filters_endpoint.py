from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.trade import Trade
from app.models.user import User
from tests.helpers import (
    assert_trade_ids,
    auth_headers,
    create_trade_in_db,
    create_user_in_db,
    normalize_to_utc,
    register_and_login,
)


def seed_trades(
    client: TestClient,
    db_session: Session,
) -> tuple[str, int, User, Trade, Trade, Trade]:
    access_token, user_id = register_and_login(client)
    other_user = create_user_in_db(db_session, "other@example.com")

    matching_newer_trade = create_trade_in_db(
        db_session,
        user_id=user_id,
        symbol="AAPL",
        side="long",
        entry_price="190.00",
        exit_price="195.00",
        quantity="10",
        opened_at=datetime(2026, 7, 16, 14, 0, tzinfo=UTC),
        closed_at=datetime(2026, 7, 16, 15, 0, tzinfo=UTC),
        pnl="50.00",
        notes="Matches several filters.",
    )
    matching_older_trade = create_trade_in_db(
        db_session,
        user_id=user_id,
        symbol="AAPL",
        side="short",
        entry_price="188.00",
        exit_price=None,
        quantity="4",
        opened_at=datetime(2026, 7, 15, 10, 0, tzinfo=UTC),
        closed_at=None,
        pnl=None,
        notes="Same symbol, different side.",
    )
    other_symbol_trade = create_trade_in_db(
        db_session,
        user_id=user_id,
        symbol="MSFT",
        side="short",
        entry_price="430.00",
        exit_price="425.00",
        quantity="3",
        opened_at=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
        closed_at=datetime(2026, 7, 14, 12, 0, tzinfo=UTC),
        pnl="15.00",
        notes="Different symbol.",
    )
    create_trade_in_db(
        db_session,
        user_id=other_user.id,
        symbol="AAPL",
        side="long",
        entry_price="200.00",
        exit_price="202.00",
        quantity="1",
        opened_at=datetime(2026, 7, 16, 16, 0, tzinfo=UTC),
        closed_at=datetime(2026, 7, 16, 17, 0, tzinfo=UTC),
        pnl="2.00",
        notes="Other user's trade.",
    )

    return (
        access_token,
        user_id,
        other_user,
        matching_newer_trade,
        matching_older_trade,
        other_symbol_trade,
    )


def test_list_trades_without_filters_returns_current_users_trades(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, user_id, _, newer_trade, older_trade, third_trade = seed_trades(
        client,
        db_session,
    )

    response = client.get(
        "/trades",
        headers=auth_headers(access_token),
    )

    response_payload = response.json()

    assert response.status_code == 200
    assert len(response_payload) == 3
    assert_trade_ids(
        response_payload,
        [newer_trade.id, older_trade.id, third_trade.id],
    )
    assert {item["user_id"] for item in response_payload} == {user_id}


def test_list_trades_filters_by_symbol(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, user_id, _, newer_trade, older_trade, _ = seed_trades(
        client,
        db_session,
    )

    response = client.get(
        "/trades?symbol=AAPL",
        headers=auth_headers(access_token),
    )

    response_payload = response.json()

    assert response.status_code == 200
    assert_trade_ids(response_payload, [newer_trade.id, older_trade.id])
    assert {item["user_id"] for item in response_payload} == {user_id}
    assert {item["symbol"] for item in response_payload} == {"AAPL"}


def test_list_trades_filters_by_side_long(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, user_id, _, newer_trade, _, _ = seed_trades(
        client,
        db_session,
    )

    response = client.get(
        "/trades?side=long",
        headers=auth_headers(access_token),
    )

    response_payload = response.json()

    assert response.status_code == 200
    assert_trade_ids(response_payload, [newer_trade.id])
    assert {item["user_id"] for item in response_payload} == {user_id}
    assert {item["side"] for item in response_payload} == {"long"}


def test_list_trades_filters_by_side_short(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, user_id, _, _, older_trade, third_trade = seed_trades(
        client,
        db_session,
    )

    response = client.get(
        "/trades?side=short",
        headers=auth_headers(access_token),
    )

    response_payload = response.json()

    assert response.status_code == 200
    assert_trade_ids(response_payload, [older_trade.id, third_trade.id])
    assert {item["user_id"] for item in response_payload} == {user_id}
    assert {item["side"] for item in response_payload} == {"short"}


def test_list_trades_filters_by_opened_from(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, user_id, _, newer_trade, older_trade, _ = seed_trades(
        client,
        db_session,
    )
    opened_from = "2026-07-15T10:00:00Z"

    response = client.get(
        f"/trades?opened_from={opened_from}",
        headers=auth_headers(access_token),
    )

    response_payload = response.json()

    assert response.status_code == 200
    assert_trade_ids(response_payload, [newer_trade.id, older_trade.id])
    assert {item["user_id"] for item in response_payload} == {user_id}
    assert all(
        normalize_to_utc(item["opened_at"]) >= normalize_to_utc(opened_from)
        for item in response_payload
    )


def test_list_trades_filters_by_opened_to(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, user_id, _, _, older_trade, third_trade = seed_trades(
        client,
        db_session,
    )
    opened_to = "2026-07-15T10:00:00Z"

    response = client.get(
        f"/trades?opened_to={opened_to}",
        headers=auth_headers(access_token),
    )

    response_payload = response.json()

    assert response.status_code == 200
    assert_trade_ids(response_payload, [older_trade.id, third_trade.id])
    assert {item["user_id"] for item in response_payload} == {user_id}
    assert all(
        normalize_to_utc(item["opened_at"]) <= normalize_to_utc(opened_to)
        for item in response_payload
    )


def test_list_trades_combines_filters(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, user_id, _, newer_trade, _, _ = seed_trades(
        client,
        db_session,
    )

    response = client.get(
        "/trades?symbol=AAPL&side=long&opened_from=2026-07-16T00:00:00Z"
        "&opened_to=2026-07-16T23:59:59Z",
        headers=auth_headers(access_token),
    )

    response_payload = response.json()

    assert response.status_code == 200
    assert_trade_ids(response_payload, [newer_trade.id])
    assert {item["user_id"] for item in response_payload} == {user_id}
    assert response_payload[0]["symbol"] == "AAPL"
    assert response_payload[0]["side"] == "long"
    assert normalize_to_utc(response_payload[0]["opened_at"]) == normalize_to_utc(
        newer_trade.opened_at
    )
    assert Decimal(response_payload[0]["entry_price"]) == Decimal("190.00")


def test_list_trades_filters_never_return_another_users_trades(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, user_id, _, newer_trade, _, _ = seed_trades(client, db_session)

    response = client.get(
        "/trades?symbol=AAPL&side=long",
        headers=auth_headers(access_token),
    )

    response_payload = response.json()

    assert response.status_code == 200
    assert_trade_ids(response_payload, [newer_trade.id])
    assert {item["user_id"] for item in response_payload} == {user_id}
    assert all(
        normalize_to_utc(item["opened_at"]) != datetime(2026, 7, 16, 16, 0, tzinfo=UTC)
        for item in response_payload
    )


def test_list_trades_invalid_side_returns_422(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, _, _, _, _, _ = seed_trades(client, db_session)

    response = client.get(
        "/trades?side=invalid",
        headers=auth_headers(access_token),
    )

    assert response.status_code == 422


def test_list_trades_invalid_datetime_returns_422(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, _, _, _, _, _ = seed_trades(client, db_session)

    response = client.get(
        "/trades?opened_from=not-a-datetime",
        headers=auth_headers(access_token),
    )

    assert response.status_code == 422


def test_list_trades_returns_unauthorized_without_token(client: TestClient) -> None:
    response = client.get("/trades")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_list_trades_returns_unauthorized_for_invalid_token(
    client: TestClient,
) -> None:
    response = client.get(
        "/trades?symbol=AAPL",
        headers=auth_headers("not-a-valid-token"),
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
