from datetime import UTC, datetime
from decimal import Decimal

from app.models.trade import Trade
from app.services.trade_stats import get_trade_stats_summary


def build_trade(
    *,
    user_id: int = 1,
    pnl: str | None,
    symbol: str = "AAPL",
    side: str = "long",
) -> Trade:
    return Trade(
        user_id=user_id,
        symbol=symbol,
        side=side,
        entry_price=Decimal("100"),
        exit_price=Decimal("100") if pnl is not None else None,
        quantity=Decimal("1"),
        opened_at=datetime(2026, 7, 16, 14, 0, tzinfo=UTC),
        closed_at=datetime(2026, 7, 16, 15, 0, tzinfo=UTC) if pnl is not None else None,
        pnl=Decimal(pnl) if pnl is not None else None,
        notes=None,
    )


class DummySession:
    pass


def test_trade_stats_service_treats_none_pnl_as_open_not_breakeven(monkeypatch) -> None:
    def fake_list_trades_for_stats(*args, **kwargs) -> list[Trade]:
        return [
            build_trade(pnl=None),
            build_trade(pnl="0"),
        ]

    monkeypatch.setattr(
        "app.services.trade_stats.list_trades_for_stats",
        fake_list_trades_for_stats,
    )

    result = get_trade_stats_summary(DummySession(), user_id=1)

    assert result.total_trades == 2
    assert result.closed_trades == 1
    assert result.breakeven_trades == 1
    assert result.winning_trades == 0
    assert result.losing_trades == 0


def test_trade_stats_service_returns_zero_average_and_win_rate_when_no_closed_trades(
    monkeypatch,
) -> None:
    def fake_list_trades_for_stats(*args, **kwargs) -> list[Trade]:
        return [
            build_trade(pnl=None),
            build_trade(pnl=None, symbol="MSFT"),
        ]

    monkeypatch.setattr(
        "app.services.trade_stats.list_trades_for_stats",
        fake_list_trades_for_stats,
    )

    result = get_trade_stats_summary(DummySession(), user_id=1)

    assert result.total_trades == 2
    assert result.closed_trades == 0
    assert result.total_pnl == Decimal("0")
    assert result.average_pnl == Decimal("0")
    assert result.win_rate == 0.0


def test_trade_stats_service_calculates_counts_and_decimal_values(monkeypatch) -> None:
    def fake_list_trades_for_stats(*args, **kwargs) -> list[Trade]:
        return [
            build_trade(pnl="50.25"),
            build_trade(pnl="-20.10", side="short"),
            build_trade(pnl="0", symbol="MSFT"),
            build_trade(pnl=None, symbol="NVDA"),
        ]

    monkeypatch.setattr(
        "app.services.trade_stats.list_trades_for_stats",
        fake_list_trades_for_stats,
    )

    result = get_trade_stats_summary(DummySession(), user_id=1)

    assert result.total_trades == 4
    assert result.closed_trades == 3
    assert result.winning_trades == 1
    assert result.losing_trades == 1
    assert result.breakeven_trades == 1
    assert result.total_pnl == Decimal("30.15")
    assert result.average_pnl == Decimal("10.05")
    assert result.win_rate == 33.33333333333333
