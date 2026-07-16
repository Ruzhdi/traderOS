from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.trade import Trade
from app.schemas.trade import TradeCreate, TradeRead, TradeUpdate


def test_trade_create_accepts_valid_data() -> None:
    opened_at = datetime.now(UTC)
    closed_at = datetime.now(UTC)

    schema = TradeCreate(
        symbol="AAPL",
        side="long",
        entry_price=Decimal("100.50"),
        exit_price=Decimal("110.25"),
        quantity=Decimal("2"),
        opened_at=opened_at,
        closed_at=closed_at,
        pnl=Decimal("19.50"),
        notes="Planned breakout trade",
    )

    assert schema.symbol == "AAPL"
    assert schema.side == "long"
    assert schema.entry_price == Decimal("100.50")
    assert schema.exit_price == Decimal("110.25")
    assert schema.quantity == Decimal("2")
    assert schema.opened_at == opened_at
    assert schema.closed_at == closed_at
    assert schema.pnl == Decimal("19.50")
    assert schema.notes == "Planned breakout trade"


def test_trade_create_rejects_invalid_side() -> None:
    with pytest.raises(ValidationError):
        TradeCreate(
            symbol="AAPL",
            side="buy",
            entry_price=Decimal("100.50"),
            quantity=Decimal("2"),
            opened_at=datetime.now(UTC),
        )


def test_trade_create_rejects_non_positive_entry_price() -> None:
    with pytest.raises(ValidationError):
        TradeCreate(
            symbol="AAPL",
            side="long",
            entry_price=Decimal("0"),
            quantity=Decimal("2"),
            opened_at=datetime.now(UTC),
        )


def test_trade_create_rejects_non_positive_quantity() -> None:
    with pytest.raises(ValidationError):
        TradeCreate(
            symbol="AAPL",
            side="long",
            entry_price=Decimal("100.50"),
            quantity=Decimal("-1"),
            opened_at=datetime.now(UTC),
        )


def test_trade_create_output_does_not_contain_user_id() -> None:
    schema = TradeCreate(
        symbol="AAPL",
        side="short",
        entry_price=Decimal("100.50"),
        quantity=Decimal("2"),
        opened_at=datetime.now(UTC),
    )

    payload = schema.model_dump()

    assert "user_id" not in payload


def test_trade_read_can_validate_orm_object() -> None:
    now = datetime.now(UTC)
    trade = Trade(
        id=1,
        user_id=10,
        symbol="AAPL",
        side="long",
        entry_price=Decimal("100.50"),
        exit_price=Decimal("110.25"),
        quantity=Decimal("2"),
        opened_at=now,
        closed_at=now,
        pnl=Decimal("19.50"),
        notes="Planned breakout trade",
        created_at=now,
        updated_at=now,
    )

    schema = TradeRead.model_validate(trade)

    assert schema.id == 1
    assert schema.user_id == 10
    assert schema.symbol == "AAPL"
    assert schema.side == "long"


def test_trade_read_output_contains_expected_fields() -> None:
    now = datetime.now(UTC)
    trade = Trade(
        id=1,
        user_id=10,
        symbol="AAPL",
        side="short",
        entry_price=Decimal("100.50"),
        exit_price=Decimal("90.25"),
        quantity=Decimal("2"),
        opened_at=now,
        closed_at=now,
        pnl=Decimal("20.50"),
        notes="Trend continuation trade",
        created_at=now,
        updated_at=now,
    )

    payload = TradeRead.model_validate(trade).model_dump()

    assert payload == {
        "id": 1,
        "user_id": 10,
        "symbol": "AAPL",
        "side": "short",
        "entry_price": Decimal("100.50"),
        "exit_price": Decimal("90.25"),
        "quantity": Decimal("2"),
        "opened_at": now,
        "closed_at": now,
        "pnl": Decimal("20.50"),
        "notes": "Trend continuation trade",
        "created_at": now,
        "updated_at": now,
    }


def test_trade_update_accepts_partial_data() -> None:
    schema = TradeUpdate(
        exit_price=Decimal("110.25"),
        closed_at=datetime.now(UTC),
        pnl=Decimal("19.50"),
    )

    assert schema.exit_price == Decimal("110.25")
    assert schema.closed_at is not None
    assert schema.pnl == Decimal("19.50")


def test_trade_update_does_not_require_all_fields() -> None:
    schema = TradeUpdate()

    assert schema.model_dump() == {
        "symbol": None,
        "side": None,
        "entry_price": None,
        "exit_price": None,
        "quantity": None,
        "opened_at": None,
        "closed_at": None,
        "pnl": None,
        "notes": None,
    }
