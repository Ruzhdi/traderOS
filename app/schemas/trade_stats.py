from decimal import Decimal

from pydantic import BaseModel


class TradeStatsRead(BaseModel):
    total_trades: int
    closed_trades: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    total_pnl: Decimal
    average_pnl: Decimal
    win_rate: float
