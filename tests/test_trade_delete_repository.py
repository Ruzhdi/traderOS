from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.trade import Trade
from app.repositories.trade import create_trade, delete_trade_for_user
from app.schemas.trade import TradeCreate
from tests.helpers import create_user_in_db


def test_delete_trade_for_user_deletes_owned_trade(db_session: Session) -> None:
    owner = create_user_in_db(db_session, "owner@example.com")
    other_user = create_user_in_db(db_session, "other@example.com")
    owned_trade = create_trade(
        db_session,
        owner.id,
        TradeCreate(
            symbol="AAPL",
            side="long",
            entry_price=Decimal("192.50"),
            exit_price=None,
            quantity=Decimal("10"),
            opened_at=datetime(2026, 7, 16, 9, 30, tzinfo=UTC),
            closed_at=None,
            pnl=None,
            notes="Owned trade.",
        ),
    )
    unrelated_trade = create_trade(
        db_session,
        other_user.id,
        TradeCreate(
            symbol="MSFT",
            side="short",
            entry_price=Decimal("430.00"),
            exit_price=None,
            quantity=Decimal("2"),
            opened_at=datetime(2026, 7, 16, 11, 0, tzinfo=UTC),
            closed_at=None,
            pnl=None,
            notes="Unrelated trade.",
        ),
    )

    deleted = delete_trade_for_user(db_session, owned_trade.id, owner.id)

    assert deleted is True
    assert db_session.get(Trade, owned_trade.id) is None
    assert db_session.get(Trade, unrelated_trade.id) is not None


def test_delete_trade_for_user_returns_false_for_missing_trade(
    db_session: Session,
) -> None:
    owner = create_user_in_db(db_session, "owner@example.com")

    deleted = delete_trade_for_user(db_session, trade_id=9999, user_id=owner.id)

    assert deleted is False


def test_delete_trade_for_user_returns_false_for_other_users_trade(
    db_session: Session,
) -> None:
    owner = create_user_in_db(db_session, "owner@example.com")
    other_user = create_user_in_db(db_session, "other@example.com")
    owner_trade = create_trade(
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
            notes="Owner trade.",
        ),
    )
    other_trade = create_trade(
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
            notes="Other user's trade.",
        ),
    )

    deleted = delete_trade_for_user(db_session, owner_trade.id, other_user.id)

    assert deleted is False
    assert db_session.get(Trade, owner_trade.id) is not None
    assert db_session.get(Trade, other_trade.id) is not None
    remaining_trade_ids = list(db_session.scalars(select(Trade.id).order_by(Trade.id)))
    assert remaining_trade_ids == [owner_trade.id, other_trade.id]
