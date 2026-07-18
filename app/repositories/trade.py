from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.trade import Trade
from app.schemas.trade import Side, TradeCreate, TradeUpdate


def create_trade(db: Session, user_id: int, trade_data: TradeCreate) -> Trade:
    trade = Trade(user_id=user_id, **trade_data.model_dump())
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return trade


def get_trade_by_id_for_user(
    db: Session,
    trade_id: int,
    user_id: int,
) -> Trade | None:
    statement = select(Trade).where(Trade.id == trade_id, Trade.user_id == user_id)
    return db.scalar(statement)


def list_trades_by_user(
    db: Session,
    user_id: int,
    symbol: str | None = None,
    side: str | None = None,
    opened_from: datetime | None = None,
    opened_to: datetime | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[Trade]:
    statement = select(Trade).where(Trade.user_id == user_id)

    if symbol is not None:
        statement = statement.where(Trade.symbol == symbol)

    if side is not None:
        statement = statement.where(Trade.side == side)

    if opened_from is not None:
        statement = statement.where(Trade.opened_at >= opened_from)

    if opened_to is not None:
        statement = statement.where(Trade.opened_at <= opened_to)

    statement = statement.order_by(Trade.opened_at.desc(), Trade.id.desc())
    statement = statement.offset(offset).limit(limit)
    return list(db.scalars(statement))


def list_trades_for_stats(
    db: Session,
    user_id: int,
    symbol: str | None = None,
    side: Side | None = None,
    opened_from: datetime | None = None,
    opened_to: datetime | None = None,
) -> list[Trade]:
    statement = select(Trade).where(Trade.user_id == user_id)

    if symbol is not None:
        statement = statement.where(Trade.symbol == symbol)

    if side is not None:
        statement = statement.where(Trade.side == side)

    if opened_from is not None:
        statement = statement.where(Trade.opened_at >= opened_from)

    if opened_to is not None:
        statement = statement.where(Trade.opened_at <= opened_to)

    statement = statement.order_by(Trade.opened_at.desc(), Trade.id.desc())
    return list(db.scalars(statement))


def update_trade_for_user(
    db: Session,
    trade_id: int,
    user_id: int,
    trade_data: TradeUpdate,
) -> Trade | None:
    trade = get_trade_by_id_for_user(db, trade_id, user_id)
    if trade is None:
        return None

    updates = trade_data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(trade, field, value)

    db.commit()
    db.refresh(trade)
    return trade


def delete_trade_for_user(
    db: Session,
    trade_id: int,
    user_id: int,
) -> bool:
    trade = get_trade_by_id_for_user(db, trade_id, user_id)
    if trade is None:
        return False

    db.delete(trade)
    db.commit()
    return True
