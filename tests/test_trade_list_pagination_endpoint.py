from datetime import UTC, datetime, timedelta
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


def seed_many_owner_trades(
    db_session: Session,
    *,
    user_id: int,
    count: int,
) -> list[Trade]:
    base_opened_at = datetime(2026, 7, 16, 15, 0, tzinfo=UTC)
    trades: list[Trade] = []

    for index in range(count):
        trades.append(
            create_trade_in_db(
                db_session,
                user_id=user_id,
                symbol="AAPL",
                side="long",
                entry_price=str(Decimal("100.00") + Decimal(index)),
                quantity="1",
                opened_at=base_opened_at - timedelta(minutes=index),
                notes=f"trade-{index}",
            )
        )

    return trades


def seed_mixed_trades(
    client: TestClient,
    db_session: Session,
) -> tuple[str, int, User, list[Trade]]:
    access_token, user_id = register_and_login(client)
    other_user = create_user_in_db(db_session, "other@example.com")

    owner_trades = [
        create_trade_in_db(
            db_session,
            user_id=user_id,
            symbol="AAPL",
            side="long",
            entry_price="101.00",
            quantity="1",
            opened_at=datetime(2026, 7, 16, 15, 0, tzinfo=UTC),
            notes="owner-0",
        ),
        create_trade_in_db(
            db_session,
            user_id=user_id,
            symbol="MSFT",
            side="short",
            entry_price="102.00",
            quantity="1",
            opened_at=datetime(2026, 7, 16, 14, 0, tzinfo=UTC),
            notes="owner-1",
        ),
        create_trade_in_db(
            db_session,
            user_id=user_id,
            symbol="AAPL",
            side="short",
            entry_price="103.00",
            quantity="1",
            opened_at=datetime(2026, 7, 16, 13, 0, tzinfo=UTC),
            notes="owner-2",
        ),
        create_trade_in_db(
            db_session,
            user_id=user_id,
            symbol="AAPL",
            side="long",
            entry_price="104.00",
            quantity="1",
            opened_at=datetime(2026, 7, 16, 12, 0, tzinfo=UTC),
            notes="owner-3",
        ),
        create_trade_in_db(
            db_session,
            user_id=user_id,
            symbol="NVDA",
            side="long",
            entry_price="105.00",
            quantity="1",
            opened_at=datetime(2026, 7, 16, 11, 0, tzinfo=UTC),
            notes="owner-4",
        ),
        create_trade_in_db(
            db_session,
            user_id=user_id,
            symbol="AAPL",
            side="short",
            entry_price="106.00",
            quantity="1",
            opened_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
            notes="owner-5",
        ),
    ]

    create_trade_in_db(
        db_session,
        user_id=other_user.id,
        symbol="AAPL",
        side="long",
        entry_price="999.00",
        quantity="5",
        opened_at=datetime(2026, 7, 16, 16, 0, tzinfo=UTC),
        notes="other-user",
    )

    return access_token, user_id, other_user, owner_trades


def test_list_trades_default_pagination_returns_current_users_trades(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, user_id = register_and_login(client)
    other_user = create_user_in_db(db_session, "other@example.com")
    owner_trades = seed_many_owner_trades(db_session, user_id=user_id, count=25)
    create_trade_in_db(
        db_session,
        user_id=other_user.id,
        symbol="TSLA",
        side="long",
        entry_price="250.00",
        quantity="1",
        opened_at=datetime(2026, 7, 16, 16, 0, tzinfo=UTC),
        notes="excluded",
    )

    response = client.get("/trades", headers=auth_headers(access_token))
    response_payload = response.json()
    expected_trades = owner_trades[:20]

    assert response.status_code == 200
    assert len(response_payload) == 20
    assert_trade_ids(response_payload, [trade.id for trade in expected_trades])
    assert {item["user_id"] for item in response_payload} == {user_id}
    assert all(item["symbol"] != "TSLA" for item in response_payload)
    assert [normalize_to_utc(item["opened_at"]) for item in response_payload] == [
        normalize_to_utc(trade.opened_at) for trade in expected_trades
    ]


def test_list_trades_limit_restricts_number_of_returned_trades(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, _, _, owner_trades = seed_mixed_trades(client, db_session)

    response = client.get(
        "/trades",
        params={"limit": 2},
        headers=auth_headers(access_token),
    )

    response_payload = response.json()

    assert response.status_code == 200
    assert len(response_payload) == 2
    assert_trade_ids(response_payload, [owner_trades[0].id, owner_trades[1].id])


def test_list_trades_offset_skips_earlier_trades(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, _, _, owner_trades = seed_mixed_trades(client, db_session)

    response = client.get(
        "/trades",
        params={"offset": 2},
        headers=auth_headers(access_token),
    )

    response_payload = response.json()

    assert response.status_code == 200
    assert_trade_ids(response_payload, [trade.id for trade in owner_trades[2:]])


def test_list_trades_limit_and_offset_work_together(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, _, _, owner_trades = seed_mixed_trades(client, db_session)

    response = client.get(
        "/trades",
        params={"limit": 2, "offset": 3},
        headers=auth_headers(access_token),
    )

    response_payload = response.json()

    assert response.status_code == 200
    assert_trade_ids(response_payload, [owner_trades[3].id, owner_trades[4].id])


def test_list_trades_pagination_works_with_symbol_filter(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, user_id, _, owner_trades = seed_mixed_trades(client, db_session)

    response = client.get(
        "/trades",
        params={"symbol": "AAPL", "limit": 2, "offset": 1},
        headers=auth_headers(access_token),
    )

    response_payload = response.json()

    assert response.status_code == 200
    assert_trade_ids(response_payload, [owner_trades[2].id, owner_trades[3].id])
    assert {item["user_id"] for item in response_payload} == {user_id}
    assert {item["symbol"] for item in response_payload} == {"AAPL"}


def test_list_trades_pagination_works_with_side_filter(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, user_id, _, owner_trades = seed_mixed_trades(client, db_session)

    response = client.get(
        "/trades",
        params={"side": "short", "limit": 1, "offset": 1},
        headers=auth_headers(access_token),
    )

    response_payload = response.json()

    assert response.status_code == 200
    assert_trade_ids(response_payload, [owner_trades[2].id])
    assert {item["user_id"] for item in response_payload} == {user_id}
    assert {item["side"] for item in response_payload} == {"short"}


def test_list_trades_pagination_never_returns_another_users_trades(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, user_id, other_user, owner_trades = seed_mixed_trades(
        client,
        db_session,
    )

    response = client.get(
        "/trades",
        params={"symbol": "AAPL", "limit": 10},
        headers=auth_headers(access_token),
    )

    response_payload = response.json()

    assert response.status_code == 200
    assert_trade_ids(
        response_payload,
        [
            owner_trades[0].id,
            owner_trades[2].id,
            owner_trades[3].id,
            owner_trades[5].id,
        ],
    )
    assert {item["user_id"] for item in response_payload} == {user_id}
    assert all(item["user_id"] != other_user.id for item in response_payload)


def test_list_trades_invalid_limit_zero_returns_422(client: TestClient) -> None:
    access_token, _ = register_and_login(client)

    response = client.get(
        "/trades",
        params={"limit": 0},
        headers=auth_headers(access_token),
    )

    assert response.status_code == 422


def test_list_trades_invalid_limit_above_max_returns_422(
    client: TestClient,
) -> None:
    access_token, _ = register_and_login(client)

    response = client.get(
        "/trades",
        params={"limit": 101},
        headers=auth_headers(access_token),
    )

    assert response.status_code == 422


def test_list_trades_invalid_offset_returns_422(client: TestClient) -> None:
    access_token, _ = register_and_login(client)

    response = client.get(
        "/trades",
        params={"offset": -1},
        headers=auth_headers(access_token),
    )

    assert response.status_code == 422


def test_list_trades_missing_token_returns_401(client: TestClient) -> None:
    response = client.get("/trades")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_list_trades_invalid_token_returns_401(client: TestClient) -> None:
    response = client.get(
        "/trades",
        headers={"Authorization": "Bearer not-a-valid-token"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
