from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.trade import create_trade, list_trades_by_user
from app.schemas.trade import TradeCreate, TradeRead

router = APIRouter(prefix="/trades", tags=["Trades"])


@router.get("", response_model=list[TradeRead], status_code=status.HTTP_200_OK)
def list_trades_for_current_user(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[TradeRead]:
    trades = list_trades_by_user(db, user_id=current_user.id)
    return [TradeRead.model_validate(trade) for trade in trades]


@router.post("", response_model=TradeRead, status_code=status.HTTP_201_CREATED)
def create_trade_for_current_user(
    trade_data: TradeCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TradeRead:
    trade = create_trade(db, user_id=current_user.id, trade_data=trade_data)
    return TradeRead.model_validate(trade)
