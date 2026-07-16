from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.trade import Trade
from app.schemas.trade import TradeCreate


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


def list_trades_by_user(db: Session, user_id: int) -> list[Trade]:
    statement = (
        select(Trade)
        .where(Trade.user_id == user_id)
        .order_by(Trade.opened_at.desc(), Trade.id.desc())
    )
    return list(db.scalars(statement))
