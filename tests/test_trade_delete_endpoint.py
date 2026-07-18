from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.helpers import auth_headers, create_trade_in_db, register_and_login


def test_delete_trade_deletes_owned_trade_and_returns_empty_204(
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
        exit_price=None,
        quantity="10",
        opened_at=datetime(2026, 7, 16, 14, 0, tzinfo=UTC),
        closed_at=None,
        pnl=None,
        notes="Delete this trade.",
    )

    response = client.delete(
        f"/trades/{trade.id}",
        headers=auth_headers(access_token),
    )

    assert response.status_code == 204
    assert response.content == b""

    get_response = client.get(
        f"/trades/{trade.id}",
        headers=auth_headers(access_token),
    )
    assert get_response.status_code == 404
    assert get_response.json() == {"detail": "Trade not found"}

    list_response = client.get(
        "/trades",
        headers=auth_headers(access_token),
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
        headers=auth_headers("not-a-valid-token"),
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_delete_trade_returns_not_found_for_other_users_trade(
    client: TestClient,
    db_session: Session,
) -> None:
    access_token, _ = register_and_login(client)
    other_access_token, other_user_id = register_and_login(
        client,
        email="other@example.com",
    )
    trade = create_trade_in_db(
        db_session,
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
        headers=auth_headers(access_token),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Trade not found"}

    owner_get_response = client.get(
        f"/trades/{trade.id}",
        headers=auth_headers(other_access_token),
    )
    assert owner_get_response.status_code == 200
    assert owner_get_response.json()["id"] == trade.id


def test_delete_trade_returns_not_found_for_missing_trade(
    client: TestClient,
) -> None:
    access_token, _ = register_and_login(client)

    response = client.delete(
        "/trades/999999",
        headers=auth_headers(access_token),
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Trade not found"}
