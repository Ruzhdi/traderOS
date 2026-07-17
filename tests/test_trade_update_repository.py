from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.repositories.trade import create_trade, update_trade_for_user
from app.repositories.user import create_user
from app.schemas.trade import TradeCreate, TradeUpdate


def to_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


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


def test_update_trade_for_user_updates_one_field_for_owner(db_session: Session) -> None:
    owner = create_user(
        db_session,
        email="owner@example.com",
        hashed_password="already-hashed-password",
    )
    trade = create_trade(
        db_session,
        owner.id,
        TradeCreate(
            symbol="AAPL",
            side="long",
            entry_price=Decimal("190.50"),
            exit_price=None,
            quantity=Decimal("5"),
            opened_at=datetime(2026, 7, 16, 9, 30, tzinfo=UTC),
            closed_at=None,
            pnl=None,
            notes="Initial note.",
        ),
    )

    updated_trade = update_trade_for_user(
        db_session,
        trade.id,
        owner.id,
        TradeUpdate(notes="Updated note."),
    )

    assert updated_trade is not None
    assert updated_trade.id == trade.id
    assert updated_trade.notes == "Updated note."
    assert updated_trade.symbol == "AAPL"
    assert updated_trade.entry_price == Decimal("190.50")
    assert updated_trade.quantity == Decimal("5")
    assert to_utc(updated_trade.opened_at) == datetime(2026, 7, 16, 9, 30, tzinfo=UTC)


def test_update_trade_for_user_updates_multiple_fields_for_owner(
    db_session: Session,
) -> None:
    owner = create_user(
        db_session,
        email="owner@example.com",
        hashed_password="already-hashed-password",
    )
    trade = create_trade(
        db_session,
        owner.id,
        TradeCreate(
            symbol="TSLA",
            side="short",
            entry_price=Decimal("250.00"),
            exit_price=None,
            quantity=Decimal("3"),
            opened_at=datetime(2026, 7, 16, 10, 0, tzinfo=UTC),
            closed_at=None,
            pnl=None,
            notes="Opening position.",
        ),
    )
    closed_at = datetime(2026, 7, 16, 14, 45, tzinfo=UTC)

    updated_trade = update_trade_for_user(
        db_session,
        trade.id,
        owner.id,
        TradeUpdate(
            exit_price=Decimal("241.25"),
            closed_at=closed_at,
            pnl=Decimal("26.25"),
            notes="Covered into weakness.",
        ),
    )

    assert updated_trade is not None
    assert updated_trade.exit_price == Decimal("241.25")
    assert to_utc(updated_trade.closed_at) == closed_at
    assert updated_trade.pnl == Decimal("26.25")
    assert updated_trade.notes == "Covered into weakness."
    assert updated_trade.side == "short"
    assert updated_trade.quantity == Decimal("3")


def test_update_trade_for_user_does_not_overwrite_missing_fields_with_none(
    db_session: Session,
) -> None:
    owner = create_user(
        db_session,
        email="owner@example.com",
        hashed_password="already-hashed-password",
    )
    original_closed_at = datetime(2026, 7, 16, 15, 0, tzinfo=UTC)
    trade = create_trade(
        db_session,
        owner.id,
        TradeCreate(
            symbol="NVDA",
            side="long",
            entry_price=Decimal("130.00"),
            exit_price=Decimal("134.50"),
            quantity=Decimal("4"),
            opened_at=datetime(2026, 7, 16, 13, 15, tzinfo=UTC),
            closed_at=original_closed_at,
            pnl=Decimal("18.00"),
            notes="Original note.",
        ),
    )

    updated_trade = update_trade_for_user(
        db_session,
        trade.id,
        owner.id,
        TradeUpdate(symbol="NVDA-W1", notes="Updated note."),
    )

    assert updated_trade is not None
    assert updated_trade.symbol == "NVDA-W1"
    assert updated_trade.notes == "Updated note."
    assert updated_trade.exit_price == Decimal("134.50")
    assert updated_trade.pnl == Decimal("18.00")
    assert to_utc(updated_trade.closed_at) == original_closed_at


def test_update_trade_for_user_returns_none_for_missing_trade(
    db_session: Session,
) -> None:
    owner = create_user(
        db_session,
        email="owner@example.com",
        hashed_password="already-hashed-password",
    )

    updated_trade = update_trade_for_user(
        db_session,
        trade_id=9999,
        user_id=owner.id,
        trade_data=TradeUpdate(notes="Missing trade."),
    )

    assert updated_trade is None


def test_update_trade_for_user_returns_none_for_other_users_trade(
    db_session: Session,
) -> None:
    owner = create_user(
        db_session,
        email="owner@example.com",
        hashed_password="already-hashed-password",
    )
    other_user = create_user(
        db_session,
        email="other@example.com",
        hashed_password="already-hashed-password",
    )
    trade = create_trade(
        db_session,
        owner.id,
        TradeCreate(
            symbol="MSFT",
            side="long",
            entry_price=Decimal("430.00"),
            exit_price=Decimal("435.50"),
            quantity=Decimal("2"),
            opened_at=datetime(2026, 7, 16, 11, 0, tzinfo=UTC),
            closed_at=datetime(2026, 7, 16, 15, 30, tzinfo=UTC),
            pnl=Decimal("11.00"),
            notes="Owner trade.",
        ),
    )

    updated_trade = update_trade_for_user(
        db_session,
        trade.id,
        other_user.id,
        TradeUpdate(notes="Not allowed.", exit_price=Decimal("999.99")),
    )

    assert updated_trade is None


def test_update_trade_for_user_leaves_other_users_trade_unchanged(
    db_session: Session,
) -> None:
    owner = create_user(
        db_session,
        email="owner@example.com",
        hashed_password="already-hashed-password",
    )
    other_user = create_user(
        db_session,
        email="other@example.com",
        hashed_password="already-hashed-password",
    )
    original_closed_at = datetime(2026, 7, 16, 15, 30, tzinfo=UTC)
    trade = create_trade(
        db_session,
        owner.id,
        TradeCreate(
            symbol="META",
            side="short",
            entry_price=Decimal("500.00"),
            exit_price=Decimal("492.00"),
            quantity=Decimal("1.5"),
            opened_at=datetime(2026, 7, 16, 12, 0, tzinfo=UTC),
            closed_at=original_closed_at,
            pnl=Decimal("12.00"),
            notes="Original owner note.",
        ),
    )

    update_trade_for_user(
        db_session,
        trade.id,
        other_user.id,
        TradeUpdate(
            symbol="META-CHANGED",
            exit_price=Decimal("480.00"),
            notes="Unauthorized update.",
        ),
    )

    unchanged_trade = update_trade_for_user(
        db_session,
        trade.id,
        owner.id,
        TradeUpdate(),
    )

    assert unchanged_trade is not None
    assert unchanged_trade.symbol == "META"
    assert unchanged_trade.exit_price == Decimal("492.00")
    assert unchanged_trade.quantity == Decimal("1.5")
    assert unchanged_trade.pnl == Decimal("12.00")
    assert unchanged_trade.notes == "Original owner note."
    assert to_utc(unchanged_trade.closed_at) == original_closed_at
