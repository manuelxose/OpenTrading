"""Simulated broker tests: EA defense-in-depth checks + deterministic matching."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from adapters.mt4.broker import BrokerConfig, SimulatedBroker, SymbolSpec, strategy_magic
from adapters.mt4.errors import Mt4ErrorCode
from adapters.mt4.protocol import (
    FillEvent,
    OrderAck,
    PartialFillEvent,
    PositionSnapshotEvent,
)
from core.clock.clocks import VirtualClock
from core.domain.enums import OrderSide, OrderType
from tests.unit.mt4.helpers import T0, make_cancel, make_modify, make_submit

EURUSD = SymbolSpec(
    initial_mid=Decimal("1.08000"),
    spread=Decimal("0.00012"),
    max_spread=Decimal("0.0003"),
)


def make_broker(**overrides: object) -> SimulatedBroker:
    config = BrokerConfig(symbols={"EURUSD": EURUSD}, **overrides)
    return SimulatedBroker(VirtualClock(T0), config, seed=42)


def test_market_buy_fills_at_ask() -> None:
    broker = make_broker()
    intent = uuid4()
    result = broker.process_submit(make_submit(order_intent_id=intent))
    assert result.reject is None
    assert isinstance(result.ack, OrderAck)
    assert result.ack.status == "FILLED"
    assert isinstance(result.events[-3], FillEvent)
    fill = result.events[-3]
    assert fill.filled_quantity == Decimal("0.10")
    assert fill.average_fill_price == broker.ask("EURUSD")
    assert fill.side is OrderSide.BUY


def test_market_sell_fills_at_bid() -> None:
    broker = make_broker()
    result = broker.process_submit(make_submit(order_intent_id=uuid4(), side=OrderSide.SELL))
    assert isinstance(result.ack, OrderAck)
    fill = next(e for e in result.events if isinstance(e, FillEvent))
    assert fill.average_fill_price == broker.bid("EURUSD")


def test_unknown_symbol_rejected() -> None:
    broker = make_broker()
    result = broker.process_submit(make_submit(order_intent_id=uuid4(), symbol="BTCUSD"))
    assert result.reject is not None
    assert result.reject.code is Mt4ErrorCode.SYMBOL_NOT_ALLOWED


def test_lot_step_invalid() -> None:
    broker = make_broker()
    result = broker.process_submit(make_submit(order_intent_id=uuid4(), quantity=Decimal("0.015")))
    assert result.reject is not None
    assert result.reject.code is Mt4ErrorCode.LOT_STEP_INVALID


def test_lot_below_minimum() -> None:
    broker = make_broker()
    result = broker.process_submit(make_submit(order_intent_id=uuid4(), quantity=Decimal("0.001")))
    assert result.reject is not None
    assert result.reject.code is Mt4ErrorCode.LOT_LIMIT_EXCEEDED


def test_insufficient_margin() -> None:
    broker = make_broker(balance=Decimal("1000"))
    result = broker.process_submit(make_submit(order_intent_id=uuid4(), quantity=Decimal("2.0")))
    assert result.reject is not None
    assert result.reject.code is Mt4ErrorCode.INSUFFICIENT_MARGIN


def test_spread_over_limit() -> None:
    wide = SymbolSpec(
        initial_mid=Decimal("1.08000"),
        spread=Decimal("0.001"),
        max_spread=Decimal("0.0003"),
    )
    broker = SimulatedBroker(VirtualClock(T0), BrokerConfig(symbols={"EURUSD": wide}), seed=42)
    result = broker.process_submit(make_submit(order_intent_id=uuid4()))
    assert result.reject is not None
    assert result.reject.code is Mt4ErrorCode.SPREAD_TOO_HIGH


def test_stop_level_violation() -> None:
    broker = make_broker()
    result = broker.process_submit(
        make_submit(
            order_intent_id=uuid4(),
            order_type=OrderType.LIMIT,
            price=Decimal("1.07990"),
            stop_loss=Decimal("1.07990"),  # too close to price
        )
    )
    assert result.reject is not None
    assert result.reject.code is Mt4ErrorCode.STOP_LEVEL_VIOLATION


def test_stale_quotes_rejected() -> None:
    clock = VirtualClock(T0)
    broker = SimulatedBroker(
        clock,
        BrokerConfig(symbols={"EURUSD": EURUSD}, max_quote_age_seconds=1.0),
        seed=42,
    )
    clock.advance(timedelta(seconds=5))  # quotes age out without stepping
    result = broker.process_submit(make_submit(order_intent_id=uuid4()))
    assert result.reject is not None
    assert result.reject.code is Mt4ErrorCode.STALE_QUOTES


def test_trading_disabled() -> None:
    broker = make_broker(trading_enabled=False)
    result = broker.process_submit(make_submit(order_intent_id=uuid4()))
    assert result.reject is not None
    assert result.reject.code is Mt4ErrorCode.TRADING_DISABLED


def test_market_closed() -> None:
    broker = make_broker(market_open=False)
    result = broker.process_submit(make_submit(order_intent_id=uuid4()))
    assert result.reject is not None
    assert result.reject.code is Mt4ErrorCode.MARKET_CLOSED


def test_invalid_magic() -> None:
    broker = make_broker(magic_whitelist=(999,))
    result = broker.process_submit(make_submit(order_intent_id=uuid4()))
    assert result.reject is not None
    assert result.reject.code is Mt4ErrorCode.INVALID_MAGIC


def test_magic_is_deterministic_from_strategy_id() -> None:
    assert strategy_magic("strategy-A") == strategy_magic("strategy-A")
    assert strategy_magic("strategy-A") != strategy_magic("strategy-B")


def test_resting_order_cancel_and_modify() -> None:
    broker = make_broker()
    intent = uuid4()
    submitted = broker.process_submit(
        make_submit(
            order_intent_id=intent,
            order_type=OrderType.LIMIT,
            price=Decimal("1.05000"),  # far below market → rests
        )
    )
    assert isinstance(submitted.ack, OrderAck)
    assert submitted.ack.status == "SUBMITTED"

    modified = broker.process_modify(
        make_modify(order_intent_id=intent, new_stop_loss=Decimal("1.04900"))
    )
    assert isinstance(modified.ack, OrderAck)
    assert modified.ack.status == "MODIFIED"

    cancelled = broker.process_cancel(make_cancel(order_intent_id=intent))
    assert isinstance(cancelled.ack, OrderAck)
    assert cancelled.ack.status == "CANCELLED"

    again = broker.process_cancel(make_cancel(order_intent_id=intent))
    assert again.reject is not None
    assert again.reject.code is Mt4ErrorCode.UNKNOWN_ORDER


def test_cancel_unknown_order_rejected() -> None:
    broker = make_broker()
    result = broker.process_cancel(make_cancel(order_intent_id=uuid4()))
    assert result.reject is not None
    assert result.reject.code is Mt4ErrorCode.UNKNOWN_ORDER


def test_modify_price_within_freeze_level_rejected() -> None:
    frozen = SymbolSpec(
        initial_mid=Decimal("1.08000"),
        freeze_level=Decimal("0.001"),
    )
    broker = SimulatedBroker(VirtualClock(T0), BrokerConfig(symbols={"EURUSD": frozen}), seed=42)
    intent = uuid4()
    submitted = broker.process_submit(
        make_submit(
            order_intent_id=intent,
            order_type=OrderType.LIMIT,
            price=Decimal("1.05000"),
        )
    )
    assert isinstance(submitted.ack, OrderAck)
    modified = broker.process_modify(
        make_modify(order_intent_id=intent, new_price=Decimal("1.05050"))
    )
    assert modified.reject is not None
    assert modified.reject.code is Mt4ErrorCode.STOP_LEVEL_VIOLATION


def test_partial_fill_then_fill() -> None:
    broker = make_broker(partial_fill_ratio=Decimal("0.5"))
    intent = uuid4()
    result = broker.process_submit(make_submit(order_intent_id=intent))
    assert isinstance(result.ack, OrderAck)
    assert result.ack.status == "SUBMITTED"  # half-filled
    partial = next(e for e in result.events if isinstance(e, PartialFillEvent))
    assert partial.filled_quantity == Decimal("0.05")
    assert partial.remaining_quantity == Decimal("0.05")

    fills = broker.advance()  # remainder fills on the next quote step
    final = next(e for e in fills if isinstance(e, FillEvent))
    assert final.filled_quantity == Decimal("0.05")
    assert broker.positions()[0].position.quantity == Decimal("0.10")


def test_fill_emits_position_and_account_snapshots() -> None:
    broker = make_broker()
    result = broker.process_submit(make_submit(order_intent_id=uuid4()))
    assert any(isinstance(e, PositionSnapshotEvent) for e in result.events)
    assert any(isinstance(e, FillEvent) for e in result.events)


def test_deterministic_across_instances() -> None:
    a = make_broker()
    b = make_broker()
    result_a = a.process_submit(make_submit(order_intent_id=uuid4()))
    result_b = b.process_submit(make_submit(order_intent_id=uuid4()))
    fill_a = next(e for e in result_a.events if isinstance(e, FillEvent))
    fill_b = next(e for e in result_b.events if isinstance(e, FillEvent))
    assert fill_a.average_fill_price == fill_b.average_fill_price
