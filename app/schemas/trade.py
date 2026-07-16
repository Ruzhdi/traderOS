from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Side = Literal["long", "short"]


class TradeCreate(BaseModel):
    symbol: str = Field(min_length=1)
    side: Side
    entry_price: Decimal = Field(gt=0)
    exit_price: Decimal | None = Field(default=None, gt=0)
    quantity: Decimal = Field(gt=0)
    opened_at: datetime
    closed_at: datetime | None = None
    pnl: Decimal | None = None
    notes: str | None = None


class TradeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    symbol: str
    side: Side
    entry_price: Decimal
    exit_price: Decimal | None
    quantity: Decimal
    opened_at: datetime
    closed_at: datetime | None
    pnl: Decimal | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class TradeUpdate(BaseModel):
    symbol: str | None = Field(default=None, min_length=1)
    side: Side | None = None
    entry_price: Decimal | None = Field(default=None, gt=0)
    exit_price: Decimal | None = Field(default=None, gt=0)
    quantity: Decimal | None = Field(default=None, gt=0)
    opened_at: datetime | None = None
    closed_at: datetime | None = None
    pnl: Decimal | None = None
    notes: str | None = None
