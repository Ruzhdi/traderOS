from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.trade import Trade
from app.repositories.trade import (
    add_trades_for_user,
    create_trade,
    get_trade_by_id_for_user,
    list_trades_by_user,
)
from app.schemas.trade import TradeCreate
from tests.helpers import create_user_in_db, normalize_to_utc


def test_create_trade_persists_trade_for_user(db_session: Session) -> None:
    user = create_user_in_db(db_session, "owner@example.com")
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
    assert normalize_to_utc(trade.opened_at) == trade_data.opened_at
    assert trade.closed_at is not None
    assert normalize_to_utc(trade.closed_at) == trade_data.closed_at
    assert trade.pnl == Decimal("62.50")
    assert trade.notes == "Earnings continuation breakout."
    assert trade.created_at is not None
    assert trade.updated_at is not None


def test_get_trade_by_id_for_user_returns_trade_for_owner(db_session: Session) -> None:
    owner = create_user_in_db(db_session, "owner@example.com")
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
    owner = create_user_in_db(db_session, "owner@example.com")
    other_user = create_user_in_db(db_session, "other@example.com")
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
    owner = create_user_in_db(db_session, "owner@example.com")
    other_user = create_user_in_db(db_session, "other@example.com")
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


def test_add_trades_for_user_stages_multiple_trades(db_session: Session) -> None:
    user = create_user_in_db(db_session, "bulk@example.com")

    staged_trades = add_trades_for_user(
        db_session,
        user_id=user.id,
        trades=[
            TradeCreate(
                symbol="AAPL",
                side="long",
                entry_price=Decimal("190.50"),
                exit_price=Decimal("194.25"),
                quantity=Decimal("2"),
                opened_at=datetime(2026, 7, 16, 9, 30, tzinfo=UTC),
                closed_at=datetime(2026, 7, 16, 10, 15, tzinfo=UTC),
                pnl=Decimal("7.50"),
                notes="First trade.",
            ),
            TradeCreate(
                symbol="MSFT",
                side="short",
                entry_price=Decimal("430.00"),
                exit_price=None,
                quantity=Decimal("1.5"),
                opened_at=datetime(2026, 7, 16, 11, 0, tzinfo=UTC),
                closed_at=None,
                pnl=None,
                notes="Second trade.",
            ),
        ],
    )

    assert len(staged_trades) == 2
    assert all(isinstance(trade, Trade) for trade in staged_trades)
    assert all(trade.id is not None for trade in staged_trades)
    assert [trade.symbol for trade in staged_trades] == ["AAPL", "MSFT"]
    assert db_session.scalars(select(Trade).order_by(Trade.id)).all() == staged_trades


def test_add_trades_for_user_assigns_owner_from_argument(db_session: Session) -> None:
    owner = create_user_in_db(db_session, "owner-bulk@example.com")

    staged_trade = add_trades_for_user(
        db_session,
        user_id=owner.id,
        trades=[
            TradeCreate(
                symbol="NVDA",
                side="long",
                entry_price=Decimal("128.50"),
                exit_price=None,
                quantity=Decimal("3"),
                opened_at=datetime(2026, 7, 16, 13, 0, tzinfo=UTC),
                closed_at=None,
                pnl=None,
                notes=None,
            )
        ],
    )[0]

    assert staged_trade.user_id == owner.id


def test_add_trades_for_user_persists_fields_after_caller_commit(
    db_session: Session,
) -> None:
    user = create_user_in_db(db_session, "commit-fields@example.com")
    trade_data = TradeCreate(
        symbol="META",
        side="short",
        entry_price=Decimal("500.00"),
        exit_price=Decimal("492.25"),
        quantity=Decimal("1"),
        opened_at=datetime(2026, 7, 16, 14, 0, tzinfo=UTC),
        closed_at=datetime(2026, 7, 16, 15, 0, tzinfo=UTC),
        pnl=Decimal("7.75"),
        notes="Committed later.",
    )

    staged_trade = add_trades_for_user(
        db_session,
        user_id=user.id,
        trades=[trade_data],
    )[0]
    db_session.commit()

    persisted_trade = get_trade_by_id_for_user(db_session, staged_trade.id, user.id)

    assert persisted_trade is not None
    assert persisted_trade.user_id == user.id
    assert persisted_trade.symbol == "META"
    assert persisted_trade.side == "short"
    assert persisted_trade.entry_price == Decimal("500.00")
    assert persisted_trade.exit_price == Decimal("492.25")
    assert persisted_trade.quantity == Decimal("1")
    assert normalize_to_utc(persisted_trade.opened_at) == trade_data.opened_at
    assert normalize_to_utc(persisted_trade.closed_at) == trade_data.closed_at
    assert persisted_trade.pnl == Decimal("7.75")
    assert persisted_trade.notes == "Committed later."


def test_add_trades_for_user_does_not_commit(db_session: Session) -> None:
    user = create_user_in_db(db_session, "no-commit@example.com")
    original_commit = db_session.commit
    commit_calls = 0

    def commit_spy() -> None:
        nonlocal commit_calls
        commit_calls += 1
        original_commit()

    db_session.commit = commit_spy
    try:
        add_trades_for_user(
            db_session,
            user_id=user.id,
            trades=[
                TradeCreate(
                    symbol="AMD",
                    side="long",
                    entry_price=Decimal("150.00"),
                    exit_price=None,
                    quantity=Decimal("4"),
                    opened_at=datetime(2026, 7, 16, 15, 30, tzinfo=UTC),
                    closed_at=None,
                    pnl=None,
                    notes=None,
                )
            ],
        )
    finally:
        db_session.commit = original_commit

    assert commit_calls == 0


def test_add_trades_for_user_rollback_removes_staged_trades(
    db_session: Session,
) -> None:
    user = create_user_in_db(db_session, "rollback@example.com")

    add_trades_for_user(
        db_session,
        user_id=user.id,
        trades=[
            TradeCreate(
                symbol="TSLA",
                side="short",
                entry_price=Decimal("250.00"),
                exit_price=None,
                quantity=Decimal("2"),
                opened_at=datetime(2026, 7, 16, 16, 0, tzinfo=UTC),
                closed_at=None,
                pnl=None,
                notes="Rolled back.",
            )
        ],
    )
    db_session.rollback()

    assert db_session.scalars(select(Trade)).all() == []


def test_add_trades_for_user_returns_empty_list_for_empty_input(
    db_session: Session,
) -> None:
    user = create_user_in_db(db_session, "empty-bulk@example.com")

    staged_trades = add_trades_for_user(
        db_session,
        user_id=user.id,
        trades=[],
    )

    assert staged_trades == []
    assert db_session.scalars(select(Trade)).all() == []
