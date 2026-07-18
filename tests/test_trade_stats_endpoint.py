from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.helpers import (
    auth_headers,
    create_trade_in_db,
    create_user_in_db,
    register_and_login,
)


def seed_trades_for_stats(
    client: TestClient,
    db_session: Session,
) -> tuple[str, int]:
    access_token, user_id = register_and_login(client)
    other_user = create_user_in_db(db_session, "other@example.com")

    create_trade_in_db(
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
        notes="Winning trade.",
    )
    create_trade_in_db(
        db_session,
        user_id=user_id,
        symbol="AAPL",
        side="short",
        entry_price="188.00",
        exit_price="190.00",
        quantity="4",
        opened_at=datetime(2026, 7, 15, 10, 0, tzinfo=UTC),
        closed_at=datetime(2026, 7, 15, 11, 0, tzinfo=UTC),
        pnl="-8.00",
        notes="Losing trade.",
    )
    create_trade_in_db(
        db_session,
        user_id=user_id,
        symbol="MSFT",
        side="short",
        entry_price="430.00",
        exit_price="430.00",
        quantity="3",
        opened_at=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
        closed_at=datetime(2026, 7, 14, 12, 0, tzinfo=UTC),
        pnl="0.00",
        notes="Breakeven trade.",
    )
    create_trade_in_db(
        db_session,
        user_id=user_id,
        symbol="AAPL",
        side="long",
        entry_price="196.00",
        exit_price=None,
        quantity="2",
        opened_at=datetime(2026, 7, 17, 8, 0, tzinfo=UTC),
        closed_at=None,
        pnl=None,
        notes="Open trade.",
    )
    create_trade_in_db(
        db_session,
        user_id=other_user.id,
        symbol="AAPL",
        side="long",
        entry_price="200.00",
        exit_price="230.00",
        quantity="1",
        opened_at=datetime(2026, 7, 16, 16, 0, tzinfo=UTC),
        closed_at=datetime(2026, 7, 16, 17, 0, tzinfo=UTC),
        pnl="30.00",
        notes="Other user's trade.",
    )

    return access_token, user_id


def assert_summary(
    payload: dict,
    *,
    total_trades: int,
    closed_trades: int,
    winning_trades: int,
    losing_trades: int,
    breakeven_trades: int,
    total_pnl: str,
    average_pnl: str,
    win_rate: float,
) -> None:
    assert payload["total_trades"] == total_trades
    assert payload["closed_trades"] == closed_trades
    assert payload["winning_trades"] == winning_trades
    assert payload["losing_trades"] == losing_trades
    assert payload["breakeven_trades"] == breakeven_trades
    assert Decimal(payload["total_pnl"]) == Decimal(total_pnl)
    assert Decimal(payload["average_pnl"]) == Decimal(average_pnl)
    assert payload["win_rate"] == win_rate


def test_trade_stats_summary_requires_authentication(client: TestClient) -> None:
    response = client.get("/trades/stats/summary")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_trade_stats_summary_rejects_invalid_token(client: TestClient) -> None:
    response = client.get(
        "/trades/stats/summary",
        headers=auth_headers("not-a-valid-token"),
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_trade_stats_summary_returns_stats_for_current_user_only(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, user_id = seed_trades_for_stats(client, db_session)

    response = client.get(
        "/trades/stats/summary",
        headers=auth_headers(access_token),
    )

    payload = response.json()

    assert response.status_code == 200
    assert user_id > 0
    assert_summary(
        payload,
        total_trades=4,
        closed_trades=3,
        winning_trades=1,
        losing_trades=1,
        breakeven_trades=1,
        total_pnl="42.00",
        average_pnl="14.00",
        win_rate=33.33333333333333,
    )


def test_trade_stats_summary_returns_zero_average_and_win_rate_without_closed_trades(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, user_id = register_and_login(client)
    create_trade_in_db(
        db_session,
        user_id=user_id,
        symbol="AAPL",
        side="long",
        entry_price="190.00",
        exit_price=None,
        quantity="10",
        opened_at=datetime(2026, 7, 16, 14, 0, tzinfo=UTC),
        closed_at=None,
        pnl=None,
        notes="Still open.",
    )

    response = client.get(
        "/trades/stats/summary",
        headers=auth_headers(access_token),
    )

    assert response.status_code == 200
    assert_summary(
        response.json(),
        total_trades=1,
        closed_trades=0,
        winning_trades=0,
        losing_trades=0,
        breakeven_trades=0,
        total_pnl="0",
        average_pnl="0",
        win_rate=0.0,
    )


def test_trade_stats_summary_filters_by_symbol(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, _ = seed_trades_for_stats(client, db_session)

    response = client.get(
        "/trades/stats/summary?symbol=AAPL",
        headers=auth_headers(access_token),
    )

    assert response.status_code == 200
    assert_summary(
        response.json(),
        total_trades=3,
        closed_trades=2,
        winning_trades=1,
        losing_trades=1,
        breakeven_trades=0,
        total_pnl="42.00",
        average_pnl="21.00",
        win_rate=50.0,
    )


def test_trade_stats_summary_filters_by_side(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, _ = seed_trades_for_stats(client, db_session)

    response = client.get(
        "/trades/stats/summary?side=short",
        headers=auth_headers(access_token),
    )

    assert response.status_code == 200
    assert_summary(
        response.json(),
        total_trades=2,
        closed_trades=2,
        winning_trades=0,
        losing_trades=1,
        breakeven_trades=1,
        total_pnl="-8.00",
        average_pnl="-4.00",
        win_rate=0.0,
    )


def test_trade_stats_summary_filters_by_opened_from(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, _ = seed_trades_for_stats(client, db_session)

    response = client.get(
        "/trades/stats/summary?opened_from=2026-07-15T10:00:00Z",
        headers=auth_headers(access_token),
    )

    assert response.status_code == 200
    assert_summary(
        response.json(),
        total_trades=3,
        closed_trades=2,
        winning_trades=1,
        losing_trades=1,
        breakeven_trades=0,
        total_pnl="42.00",
        average_pnl="21.00",
        win_rate=50.0,
    )


def test_trade_stats_summary_filters_by_opened_to(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, _ = seed_trades_for_stats(client, db_session)

    response = client.get(
        "/trades/stats/summary?opened_to=2026-07-15T10:00:00Z",
        headers=auth_headers(access_token),
    )

    assert response.status_code == 200
    assert_summary(
        response.json(),
        total_trades=2,
        closed_trades=2,
        winning_trades=0,
        losing_trades=1,
        breakeven_trades=1,
        total_pnl="-8.00",
        average_pnl="-4.00",
        win_rate=0.0,
    )


def test_trade_stats_summary_combines_filters(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, _ = seed_trades_for_stats(client, db_session)

    response = client.get(
        "/trades/stats/summary?symbol=AAPL&side=long&opened_from=2026-07-16T00:00:00Z"
        "&opened_to=2026-07-17T23:59:59Z",
        headers=auth_headers(access_token),
    )

    assert response.status_code == 200
    assert_summary(
        response.json(),
        total_trades=2,
        closed_trades=1,
        winning_trades=1,
        losing_trades=0,
        breakeven_trades=0,
        total_pnl="50.00",
        average_pnl="50.00",
        win_rate=100.0,
    )


def test_trade_stats_summary_invalid_side_returns_422(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, _ = seed_trades_for_stats(client, db_session)

    response = client.get(
        "/trades/stats/summary?side=invalid",
        headers=auth_headers(access_token),
    )

    assert response.status_code == 422


def test_trade_stats_summary_invalid_datetime_returns_422(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, _ = seed_trades_for_stats(client, db_session)

    response = client.get(
        "/trades/stats/summary?opened_from=not-a-datetime",
        headers=auth_headers(access_token),
    )

    assert response.status_code == 422
