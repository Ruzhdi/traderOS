from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.models.user import User
from app.repositories.user import create_user, get_user_by_id


@pytest.fixture
def db_session() -> Generator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_get_user_by_id_returns_existing_user(db_session: Session) -> None:
    created_user = create_user(
        db_session,
        email="user@example.com",
        hashed_password="already-hashed-password",
    )

    found_user = get_user_by_id(db_session, created_user.id)

    assert found_user is not None
    assert found_user.id == created_user.id
    assert found_user.email == created_user.email


def test_get_user_by_id_returns_none_for_missing_user(db_session: Session) -> None:
    found_user = get_user_by_id(db_session, 999999)

    assert found_user is None


@pytest.fixture
def client() -> Generator[TestClient]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    test_app = FastAPI()
    test_app.dependency_overrides[get_db] = override_get_db

    @test_app.get("/test-protected")
    def protected_route(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> dict[str, int | str]:
        return {"id": current_user.id, "email": current_user.email}

    with TestClient(test_app) as test_client:
        yield test_client

    test_app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def create_test_user(client: TestClient) -> User:
    db_generator = client.app.dependency_overrides[get_db]()
    db = next(db_generator)
    try:
        user = User(
            email="user@example.com",
            hashed_password=hash_password("strongpass"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db_generator.close()


def create_expired_token(subject: str) -> str:
    settings = get_settings()
    return jwt.encode(
        {"sub": subject, "exp": datetime.now(UTC) - timedelta(minutes=1)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def test_protected_route_returns_current_user_for_valid_token(
    client: TestClient,
) -> None:
    user = create_test_user(client)
    token = create_access_token(str(user.id))

    response = client.get(
        "/test-protected",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"id": user.id, "email": user.email}


def test_protected_route_returns_unauthorized_for_missing_token(
    client: TestClient,
) -> None:
    response = client.get("/test-protected")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_protected_route_returns_unauthorized_for_invalid_token(
    client: TestClient,
) -> None:
    response = client.get(
        "/test-protected",
        headers={"Authorization": "Bearer not-a-valid-token"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_protected_route_returns_unauthorized_for_expired_token(
    client: TestClient,
) -> None:
    token = create_expired_token("1")

    response = client.get(
        "/test-protected",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_protected_route_returns_unauthorized_for_missing_sub_claim(
    client: TestClient,
) -> None:
    settings = get_settings()
    token = jwt.encode(
        {"exp": datetime.now(UTC) + timedelta(minutes=5)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    response = client.get(
        "/test-protected",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_protected_route_returns_unauthorized_for_non_integer_sub(
    client: TestClient,
) -> None:
    token = create_access_token("not-an-integer")

    response = client.get(
        "/test-protected",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_protected_route_returns_unauthorized_for_non_existing_user(
    client: TestClient,
) -> None:
    token = create_access_token("999999")

    response = client.get(
        "/test-protected",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
