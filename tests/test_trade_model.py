from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.trade import Trade
from tests.helpers import create_user_in_db


def test_trade_can_be_created_and_selected_for_a_user(db_session: Session) -> None:
    user = create_user_in_db(db_session, "trader@example.com")

    opened_at = datetime(2026, 7, 16, 9, 30, tzinfo=UTC)
    closed_at = datetime(2026, 7, 16, 15, 45, tzinfo=UTC)

    trade = Trade(
        user_id=user.id,
        symbol="AAPL",
        side="buy",
        entry_price=Decimal("192.50"),
        exit_price=Decimal("198.75"),
        quantity=Decimal("10"),
        opened_at=opened_at,
        closed_at=closed_at,
        pnl=Decimal("62.50"),
        notes="Earnings continuation breakout.",
    )
    db_session.add(trade)
    db_session.commit()

    stored_trade = db_session.scalar(select(Trade).where(Trade.id == trade.id))

    assert stored_trade is not None
    assert stored_trade.user_id == user.id
    assert stored_trade.symbol == "AAPL"
    assert stored_trade.side == "buy"
    assert stored_trade.entry_price == Decimal("192.50")
    assert stored_trade.exit_price == Decimal("198.75")
    assert stored_trade.quantity == Decimal("10")
    assert stored_trade.opened_at.replace(tzinfo=UTC) == opened_at
    assert stored_trade.closed_at is not None
    assert stored_trade.closed_at.replace(tzinfo=UTC) == closed_at
    assert stored_trade.pnl == Decimal("62.50")
    assert stored_trade.notes == "Earnings continuation breakout."
    assert stored_trade.created_at is not None
    assert stored_trade.updated_at is not None
