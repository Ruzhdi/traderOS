from fastapi.testclient import TestClient


def test_register_user_returns_created_user(client: TestClient) -> None:
    response = client.post(
        "/auth/register",
        json={"email": "user@example.com", "password": "strongpass"},
    )

    payload = response.json()

    assert response.status_code == 201
    assert payload["id"] is not None
    assert payload["email"] == "user@example.com"
    assert payload["is_active"] is True
    assert payload["created_at"]
    assert payload["updated_at"]
    assert "password" not in payload
    assert "hashed_password" not in payload


def test_register_user_returns_conflict_for_duplicate_email(
    client: TestClient,
) -> None:
    payload = {"email": "user@example.com", "password": "strongpass"}

    first_response = client.post("/auth/register", json=payload)
    second_response = client.post("/auth/register", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409


def test_register_user_returns_validation_error_for_invalid_payload(
    client: TestClient,
) -> None:
    response = client.post(
        "/auth/register",
        json={"email": "not-an-email", "password": "short"},
    )

    assert response.status_code == 422
