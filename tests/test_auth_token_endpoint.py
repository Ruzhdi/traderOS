from fastapi.testclient import TestClient

from tests.helpers import auth_headers


def test_token_endpoint_returns_access_token_and_supports_auth_me(
    client: TestClient,
) -> None:
    credentials = {"email": "user@example.com", "password": "strongpass"}

    register_response = client.post("/auth/register", json=credentials)
    assert register_response.status_code == 201

    token_response = client.post(
        "/auth/token",
        data={"username": credentials["email"], "password": credentials["password"]},
    )

    payload = token_response.json()

    assert token_response.status_code == 200
    assert payload["access_token"]
    assert payload["token_type"] == "bearer"

    me_response = client.get(
        "/auth/me",
        headers=auth_headers(payload["access_token"]),
    )

    assert me_response.status_code == 200
    assert me_response.json()["email"] == credentials["email"]


def test_token_endpoint_returns_unauthorized_for_unknown_user(
    client: TestClient,
) -> None:
    response = client.post(
        "/auth/token",
        data={"username": "missing@example.com", "password": "strongpass"},
    )

    assert response.status_code == 401


def test_token_endpoint_returns_unauthorized_for_wrong_password(
    client: TestClient,
) -> None:
    credentials = {"email": "user@example.com", "password": "strongpass"}

    register_response = client.post("/auth/register", json=credentials)
    assert register_response.status_code == 201

    response = client.post(
        "/auth/token",
        data={"username": credentials["email"], "password": "wrongpass"},
    )

    assert response.status_code == 401


def test_json_login_flow_still_returns_access_token_and_supports_auth_me(
    client: TestClient,
) -> None:
    credentials = {"email": "user@example.com", "password": "strongpass"}

    register_response = client.post("/auth/register", json=credentials)
    assert register_response.status_code == 201

    login_response = client.post("/auth/login", json=credentials)
    payload = login_response.json()

    assert login_response.status_code == 200
    assert payload["access_token"]
    assert payload["token_type"] == "bearer"

    me_response = client.get(
        "/auth/me",
        headers=auth_headers(payload["access_token"]),
    )

    assert me_response.status_code == 200
    assert me_response.json()["email"] == credentials["email"]
