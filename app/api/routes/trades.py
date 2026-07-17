from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.trade import (
    create_trade,
    delete_trade_for_user,
    get_trade_by_id_for_user,
    list_trades_by_user,
    update_trade_for_user,
)
from app.schemas.trade import Side, TradeCreate, TradeRead, TradeUpdate

router = APIRouter(prefix="/trades", tags=["Trades"])


@router.get("", response_model=list[TradeRead], status_code=status.HTTP_200_OK)
def list_trades_for_current_user(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    symbol: str | None = None,
    side: Side | None = None,
    opened_from: datetime | None = None,
    opened_to: datetime | None = None,
) -> list[TradeRead]:
    trades = list_trades_by_user(
        db,
        user_id=current_user.id,
        symbol=symbol,
        side=side,
        opened_from=opened_from,
        opened_to=opened_to,
    )
    return [TradeRead.model_validate(trade) for trade in trades]


@router.get("/{trade_id}", response_model=TradeRead, status_code=status.HTTP_200_OK)
def get_trade_for_current_user(
    trade_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TradeRead:
    trade = get_trade_by_id_for_user(db, trade_id=trade_id, user_id=current_user.id)
    if trade is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trade not found",
        )

    return TradeRead.model_validate(trade)


@router.post("", response_model=TradeRead, status_code=status.HTTP_201_CREATED)
def create_trade_for_current_user(
    trade_data: TradeCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TradeRead:
    trade = create_trade(db, user_id=current_user.id, trade_data=trade_data)
    return TradeRead.model_validate(trade)


@router.patch("/{trade_id}", response_model=TradeRead, status_code=status.HTTP_200_OK)
def update_trade_for_current_user(
    trade_id: int,
    trade_data: TradeUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TradeRead:
    trade = update_trade_for_user(
        db,
        trade_id=trade_id,
        user_id=current_user.id,
        trade_data=trade_data,
    )
    if trade is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trade not found",
        )

    return TradeRead.model_validate(trade)


@router.delete("/{trade_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trade_for_current_user(
    trade_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Response:
    deleted = delete_trade_for_user(
        db,
        trade_id=trade_id,
        user_id=current_user.id,
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Trade not found",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
