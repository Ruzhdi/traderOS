from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.user import User
from app.repositories.user import create_user, get_user_by_email


@pytest.fixture
def db_session() -> Generator[Session]:
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_create_user_creates_a_user(db_session: Session) -> None:
    user = create_user(
        db_session,
        email="user@example.com",
        hashed_password="already-hashed-password",
    )

    assert isinstance(user, User)
    assert user.id is not None
    assert user.email == "user@example.com"
    assert user.hashed_password == "already-hashed-password"


def test_get_user_by_email_returns_existing_user(db_session: Session) -> None:
    created_user = create_user(
        db_session,
        email="user@example.com",
        hashed_password="already-hashed-password",
    )

    found_user = get_user_by_email(db_session, "user@example.com")

    assert found_user is not None
    assert found_user.id == created_user.id
    assert found_user.email == created_user.email


def test_get_user_by_email_returns_none_for_missing_email(
    db_session: Session,
) -> None:
    found_user = get_user_by_email(db_session, "missing@example.com")

    assert found_user is None
