from fastapi.testclient import TestClient

from tests.helpers import auth_headers, register_and_login


def test_auth_me_returns_current_user_data(client: TestClient) -> None:
    access_token, _ = register_and_login(client)

    response = client.get(
        "/auth/me",
        headers=auth_headers(access_token),
    )

    payload = response.json()

    assert response.status_code == 200
    assert payload["id"]
    assert payload["email"] == "user@example.com"
    assert payload["is_active"] is True
    assert payload["created_at"]
    assert payload["updated_at"]
    assert "password" not in payload
    assert "hashed_password" not in payload


def test_auth_me_returns_unauthorized_without_token(client: TestClient) -> None:
    response = client.get("/auth/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_auth_me_returns_unauthorized_for_invalid_token(client: TestClient) -> None:
    response = client.get(
        "/auth/me",
        headers=auth_headers("not-a-valid-token"),
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
