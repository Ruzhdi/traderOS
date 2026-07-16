from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models.trade import Trade
from app.repositories.trade import (
    create_trade,
    get_trade_by_id_for_user,
    list_trades_by_user,
)
from app.repositories.user import create_user
from app.schemas.trade import TradeCreate


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


def test_create_trade_persists_trade_for_user(db_session: Session) -> None:
    user = create_user(
        db_session,
        email="owner@example.com",
        hashed_password="already-hashed-password",
    )
    trade_data = TradeCreate(
        symbol="AAPL",
        side="long",
        entry_price=Decimal("192.50"),
        exit_price=Decimal("198.75"),
        quantity=Decimal("10"),
        opened_at=datetime(2026, 7, 16, 9, 30, tzinfo=UTC),
        closed_at=datetime(2026, 7, 16, 15, 45, tzinfo=UTC),
        pnl=Decimal("62.50"),
        notes="Earnings continuation breakout.",
    )

    trade = create_trade(db_session, user.id, trade_data)

    assert isinstance(trade, Trade)
    assert trade.id is not None
    assert trade.user_id == user.id
    assert trade.symbol == "AAPL"
    assert trade.side == "long"
    assert trade.entry_price == Decimal("192.50")
    assert trade.exit_price == Decimal("198.75")
    assert trade.quantity == Decimal("10")
    assert trade.opened_at.replace(tzinfo=UTC) == trade_data.opened_at
    assert trade.closed_at is not None
    assert trade.closed_at.replace(tzinfo=UTC) == trade_data.closed_at
    assert trade.pnl == Decimal("62.50")
    assert trade.notes == "Earnings continuation breakout."
    assert trade.created_at is not None
    assert trade.updated_at is not None


def test_get_trade_by_id_for_user_returns_trade_for_owner(db_session: Session) -> None:
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

    found_trade = get_trade_by_id_for_user(db_session, trade.id, owner.id)

    assert found_trade is not None
    assert found_trade.id == trade.id
    assert found_trade.user_id == owner.id


def test_get_trade_by_id_for_user_returns_none_for_other_user(
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
            exit_price=None,
            quantity=Decimal("5"),
            opened_at=datetime(2026, 7, 16, 11, 0, tzinfo=UTC),
            closed_at=None,
            pnl=None,
            notes=None,
        ),
    )

    found_trade = get_trade_by_id_for_user(db_session, trade.id, other_user.id)

    assert found_trade is None


def test_list_trades_by_user_returns_only_owned_trades(db_session: Session) -> None:
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
    older_trade = create_trade(
        db_session,
        owner.id,
        TradeCreate(
            symbol="AAPL",
            side="long",
            entry_price=Decimal("190.00"),
            exit_price=None,
            quantity=Decimal("2"),
            opened_at=datetime(2026, 7, 16, 9, 30, tzinfo=UTC),
            closed_at=None,
            pnl=None,
            notes="Earlier trade.",
        ),
    )
    newer_trade = create_trade(
        db_session,
        owner.id,
        TradeCreate(
            symbol="NVDA",
            side="long",
            entry_price=Decimal("130.00"),
            exit_price=Decimal("132.00"),
            quantity=Decimal("4"),
            opened_at=datetime(2026, 7, 16, 13, 15, tzinfo=UTC),
            closed_at=datetime(2026, 7, 16, 14, 0, tzinfo=UTC),
            pnl=Decimal("8.00"),
            notes="Later trade.",
        ),
    )
    create_trade(
        db_session,
        other_user.id,
        TradeCreate(
            symbol="META",
            side="short",
            entry_price=Decimal("500.00"),
            exit_price=None,
            quantity=Decimal("1"),
            opened_at=datetime(2026, 7, 16, 12, 0, tzinfo=UTC),
            closed_at=None,
            pnl=None,
            notes="Another user's trade.",
        ),
    )

    trades = list_trades_by_user(db_session, owner.id)

    assert [trade.id for trade in trades] == [newer_trade.id, older_trade.id]
    assert all(trade.user_id == owner.id for trade in trades)
    assert {trade.symbol for trade in trades} == {"AAPL", "NVDA"}
