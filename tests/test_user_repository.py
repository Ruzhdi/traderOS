from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.user import get_user_by_email
from tests.helpers import create_user_in_db


def test_create_user_creates_a_user(db_session: Session) -> None:
    user = create_user_in_db(db_session, "user@example.com")

    assert isinstance(user, User)
    assert user.id is not None
    assert user.email == "user@example.com"
    assert user.hashed_password == "already-hashed-password"


def test_get_user_by_email_returns_existing_user(db_session: Session) -> None:
    created_user = create_user_in_db(db_session, "user@example.com")

    found_user = get_user_by_email(db_session, "user@example.com")

    assert found_user is not None
    assert found_user.id == created_user.id
    assert found_user.email == created_user.email


def test_get_user_by_email_returns_none_for_missing_email(
    db_session: Session,
) -> None:
    found_user = get_user_by_email(db_session, "missing@example.com")

    assert found_user is None
