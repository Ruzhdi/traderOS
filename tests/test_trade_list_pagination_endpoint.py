from collections.abc import Generator
from datetime import UTC, datetime, timedelta
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
    testing_session_local = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session]:
        db = testing_session_local()
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
    quantity: str,
    opened_at: datetime,
    notes: str | None = None,
) -> Trade:
    db_generator = client.app.dependency_overrides[get_db]()
    db = next(db_generator)
    try:
        trade = Trade(
            user_id=user_id,
            symbol=symbol,
            side=side,
            entry_price=Decimal(entry_price),
            exit_price=None,
            quantity=Decimal(quantity),
            opened_at=opened_at,
            closed_at=None,
            pnl=None,
            notes=notes,
        )
        db.add(trade)
        db.commit()
        db.refresh(trade)
        return trade
    finally:
        db_generator.close()


def auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def normalize_to_utc(value: str | datetime) -> datetime:
    dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def assert_trade_ids(response_payload: list[dict], expected_ids: list[int]) -> None:
    assert [item["id"] for item in response_payload] == expected_ids


def seed_many_owner_trades(
    client: TestClient,
    *,
    user_id: int,
    count: int,
) -> list[Trade]:
    base_opened_at = datetime(2026, 7, 16, 15, 0, tzinfo=UTC)
    trades: list[Trade] = []

    for index in range(count):
        trades.append(
            create_trade_in_db(
                client,
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


def seed_mixed_trades(client: TestClient) -> tuple[str, int, User, list[Trade]]:
    access_token, user_id = register_and_login(client)
    other_user = create_user_in_db(client, "other@example.com")

    owner_trades = [
        create_trade_in_db(
            client,
            user_id=user_id,
            symbol="AAPL",
            side="long",
            entry_price="101.00",
            quantity="1",
            opened_at=datetime(2026, 7, 16, 15, 0, tzinfo=UTC),
            notes="owner-0",
        ),
        create_trade_in_db(
            client,
            user_id=user_id,
            symbol="MSFT",
            side="short",
            entry_price="102.00",
            quantity="1",
            opened_at=datetime(2026, 7, 16, 14, 0, tzinfo=UTC),
            notes="owner-1",
        ),
        create_trade_in_db(
            client,
            user_id=user_id,
            symbol="AAPL",
            side="short",
            entry_price="103.00",
            quantity="1",
            opened_at=datetime(2026, 7, 16, 13, 0, tzinfo=UTC),
            notes="owner-2",
        ),
        create_trade_in_db(
            client,
            user_id=user_id,
            symbol="AAPL",
            side="long",
            entry_price="104.00",
            quantity="1",
            opened_at=datetime(2026, 7, 16, 12, 0, tzinfo=UTC),
            notes="owner-3",
        ),
        create_trade_in_db(
            client,
            user_id=user_id,
            symbol="NVDA",
            side="long",
            entry_price="105.00",
            quantity="1",
            opened_at=datetime(2026, 7, 16, 11, 0, tzinfo=UTC),
            notes="owner-4",
        ),
        create_trade_in_db(
            client,
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
        client,
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
) -> None:
    access_token, user_id = register_and_login(client)
    other_user = create_user_in_db(client, "other@example.com")
    owner_trades = seed_many_owner_trades(client, user_id=user_id, count=25)
    create_trade_in_db(
        client,
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
) -> None:
    access_token, _, _, owner_trades = seed_mixed_trades(client)

    response = client.get(
        "/trades",
        params={"limit": 2},
        headers=auth_headers(access_token),
    )

    response_payload = response.json()

    assert response.status_code == 200
    assert len(response_payload) == 2
    assert_trade_ids(response_payload, [owner_trades[0].id, owner_trades[1].id])


def test_list_trades_offset_skips_earlier_trades(client: TestClient) -> None:
    access_token, _, _, owner_trades = seed_mixed_trades(client)

    response = client.get(
        "/trades",
        params={"offset": 2},
        headers=auth_headers(access_token),
    )

    response_payload = response.json()

    assert response.status_code == 200
    assert_trade_ids(response_payload, [trade.id for trade in owner_trades[2:]])


def test_list_trades_limit_and_offset_work_together(client: TestClient) -> None:
    access_token, _, _, owner_trades = seed_mixed_trades(client)

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
) -> None:
    access_token, user_id, _, owner_trades = seed_mixed_trades(client)

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


def test_list_trades_pagination_works_with_side_filter(client: TestClient) -> None:
    access_token, user_id, _, owner_trades = seed_mixed_trades(client)

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
) -> None:
    access_token, user_id, other_user, owner_trades = seed_mixed_trades(client)

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
