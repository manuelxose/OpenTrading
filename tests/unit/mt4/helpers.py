"""Shared builders for the MT4 protocol test suite (tests/unit/mt4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from adapters.mt4.protocol import (
    CancelOrderCommand,
    ModifyOrderCommand,
    SubmitOrderCommand,
)
from core.clock.clocks import VirtualClock
from core.domain.enums import OrderSide, OrderType, TimeInForce

__all__ = ["T0", "make_cancel", "make_modify", "make_submit", "new_clock"]

T0 = datetime(2026, 8, 26, 10, 0, 0, tzinfo=UTC)


def new_clock() -> VirtualClock:
    return VirtualClock(T0)


def make_submit(
    *,
    sequence: int = 1,
    order_intent_id: UUID | None = None,
    strategy_id: str = "strategy-A",
    strategy_version: str = "1.0.0",
    symbol: str = "EURUSD",
    side: OrderSide = OrderSide.BUY,
    quantity: Decimal = Decimal("0.10"),
    order_type: OrderType = OrderType.MARKET,
    price: Decimal | None = None,
    stop_loss: Decimal | None = None,
    take_profit: Decimal | None = None,
    max_slippage: Decimal = Decimal("0.0003"),
    timestamp: datetime = T0,
    expires_in_seconds: int = 60,
    message_id: UUID | None = None,
) -> SubmitOrderCommand:
    return SubmitOrderCommand(
        message_id=message_id or uuid4(),
        timestamp=timestamp,
        sequence=sequence,
        order_intent_id=order_intent_id or uuid4(),
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        expires_at=timestamp + timedelta(seconds=expires_in_seconds),
        symbol=symbol,
        side=side,
        quantity=quantity,
        order_type=order_type,
        price=price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        max_slippage=max_slippage,
        time_in_force=TimeInForce.GTC,
    )


def make_cancel(
    *,
    sequence: int = 2,
    order_intent_id: UUID,
    strategy_id: str = "strategy-A",
    symbol: str = "EURUSD",
    side: OrderSide = OrderSide.BUY,
    quantity: Decimal = Decimal("0.10"),
    order_type: OrderType = OrderType.MARKET,
    timestamp: datetime = T0,
) -> CancelOrderCommand:
    return CancelOrderCommand(
        message_id=uuid4(),
        timestamp=timestamp,
        sequence=sequence,
        order_intent_id=order_intent_id,
        strategy_id=strategy_id,
        strategy_version="1.0.0",
        expires_at=timestamp + timedelta(seconds=60),
        symbol=symbol,
        side=side,
        quantity=quantity,
        order_type=order_type,
    )


def make_modify(
    *,
    sequence: int = 2,
    order_intent_id: UUID,
    new_stop_loss: Decimal | None = None,
    new_take_profit: Decimal | None = None,
    new_price: Decimal | None = None,
    timestamp: datetime = T0,
) -> ModifyOrderCommand:
    return ModifyOrderCommand(
        message_id=uuid4(),
        timestamp=timestamp,
        sequence=sequence,
        order_intent_id=order_intent_id,
        strategy_id="strategy-A",
        strategy_version="1.0.0",
        expires_at=timestamp + timedelta(seconds=60),
        symbol="EURUSD",
        side=OrderSide.BUY,
        quantity=Decimal("0.10"),
        order_type=OrderType.LIMIT,
        new_price=new_price,
        new_stop_loss=new_stop_loss,
        new_take_profit=new_take_profit,
    )
