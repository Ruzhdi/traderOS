from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.repositories.trade import list_trades_for_stats
from app.schemas.trade import Side
from app.schemas.trade_stats import TradeStatsRead


def get_trade_stats_summary(
    db: Session,
    user_id: int,
    symbol: str | None = None,
    side: Side | None = None,
    opened_from: datetime | None = None,
    opened_to: datetime | None = None,
) -> TradeStatsRead:
    trades = list_trades_for_stats(
        db,
        user_id=user_id,
        symbol=symbol,
        side=side,
        opened_from=opened_from,
        opened_to=opened_to,
    )

    total_trades = len(trades)
    closed_trades = 0
    winning_trades = 0
    losing_trades = 0
    breakeven_trades = 0
    total_pnl = Decimal("0")

    for trade in trades:
        if trade.pnl is None:
            continue

        closed_trades += 1
        total_pnl += trade.pnl

        if trade.pnl > 0:
            winning_trades += 1
        elif trade.pnl < 0:
            losing_trades += 1
        else:
            breakeven_trades += 1

    average_pnl = total_pnl / closed_trades if closed_trades else Decimal("0")
    win_rate = winning_trades / closed_trades * 100 if closed_trades else 0.0

    return TradeStatsRead(
        total_trades=total_trades,
        closed_trades=closed_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        breakeven_trades=breakeven_trades,
        total_pnl=total_pnl,
        average_pnl=average_pnl,
        win_rate=win_rate,
    )
