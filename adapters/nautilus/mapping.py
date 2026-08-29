"""Bidirectional mappings between OpenTrading domain contracts and NautilusTrader objects.

This is the only translation point between the two worlds (ADR-0007, INV-2):

- domain ``Instrument`` → Nautilus ``CurrencyPair``;
- domain ``OrderIntent`` → Nautilus ``MarketOrder`` / ``LimitOrder`` /
  ``StopMarketOrder`` / ``StopLimitOrder`` (the same mapping function serves
  BACKTEST, PAPER and LIVE — only the venue behind it changes);
- Nautilus order/position events → domain ``ExecutionReport`` / ``PositionSnapshot`` /
  ``TradeOutcome``.

Domain models are never moved into Nautilus and Nautilus objects never leak into
``core/`` (enforced by ``tests/unit/domain/test_import_guard.py``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid5
from uuid import uuid4 as _random_uuid4

from core.domain.enums import (
    AssetClass,
    ExecutionState,
    OrderSide,
    OrderType,
    PositionSide,
    SignalDirection,
    TimeInForce,
)
from core.schemas import ExecutionReport, Instrument, OrderIntent, PositionSnapshot, TradeOutcome
from core.schemas.base import Provenance
from nautilus_trader.core.datetime import unix_nanos_to_dt
from nautilus_trader.core.uuid import UUID4
from nautilus_trader.model.enums import (
    OrderSide as NOrderSide,
)
from nautilus_trader.model.enums import (
    PositionSide as NPositionSide,
)
from nautilus_trader.model.enums import (
    TimeInForce as NTimeInForce,
)
from nautilus_trader.model.enums import (
    TriggerType,
)
from nautilus_trader.model.events import (
    OrderAccepted,
    OrderDenied,
    OrderFilled,
    OrderRejected,
    OrderSubmitted,
    PositionChanged,
    PositionClosed,
    PositionOpened,
)
from nautilus_trader.model.identifiers import (
    ClientOrderId,
    InstrumentId,
    StrategyId,
    Symbol,
    TraderId,
    Venue,
)
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Currency, Price, Quantity
from nautilus_trader.model.orders import (
    LimitOrder,
    MarketOrder,
    StopLimitOrder,
    StopMarketOrder,
)

#: Namespaces for deterministic (seed-independent, content-derived) UUIDs.
REPORT_NS = UUID("9b3b1c9f-0000-4f01-9a00-000000000007")
TRADE_NS = UUID("9b3b1c9f-0000-4f01-9a00-000000000008")

PRODUCER = "adapters.nautilus"

_SIDE_MAP: dict[OrderSide, NOrderSide] = {
    OrderSide.BUY: NOrderSide.BUY,
    OrderSide.SELL: NOrderSide.SELL,
}

_TIF_MAP: dict[TimeInForce, NTimeInForce] = {
    TimeInForce.GTC: NTimeInForce.GTC,
    TimeInForce.DAY: NTimeInForce.DAY,
    TimeInForce.IOC: NTimeInForce.IOC,
    TimeInForce.FOK: NTimeInForce.FOK,
}


def provenance(produced_at: datetime) -> Provenance:
    return Provenance(producer=PRODUCER, produced_at=produced_at)


def _to_utc(ts_ns: int) -> datetime:
    dt = cast(datetime, unix_nanos_to_dt(ts_ns))
    return dt.astimezone(UTC)


def _decimal(value: object) -> Decimal:
    """Lossless Decimal view of a Nautilus Price/Quantity/Money/double field."""
    return Decimal(str(value))


def instrument_to_nautilus(instrument: Instrument, venue: Venue) -> CurrencyPair:
    """Map the canonical domain ``Instrument`` to a Nautilus spot ``CurrencyPair``.

    Only FX is mapped today (ADR-0007 Phase 4 scope); other asset classes raise.
    """
    if instrument.asset_class is not AssetClass.FX:
        raise NotImplementedError(
            f"instrument_to_nautilus supports FX only (got {instrument.asset_class.value})"
        )
    if not instrument.base_currency or not instrument.quote_currency:
        raise ValueError("FX instrument requires base_currency and quote_currency")
    return CurrencyPair(
        instrument_id=InstrumentId(symbol=Symbol(instrument.symbol), venue=venue),
        raw_symbol=Symbol(instrument.symbol),
        base_currency=Currency.from_str(instrument.base_currency),
        quote_currency=Currency.from_str(instrument.quote_currency),
        price_precision=instrument.price_precision,
        size_precision=0,
        price_increment=Price.from_str(str(instrument.tick_size)),
        size_increment=Quantity(instrument.lot_size * instrument.lot_step, 0),
        ts_event=0,
        ts_init=0,
        multiplier=Quantity.from_int(1),
        min_quantity=Quantity(instrument.min_lot * instrument.lot_size, 0),
        max_quantity=Quantity(instrument.max_lot * instrument.lot_size, 0),
        info={
            "exchange": instrument.exchange,
            "asset_class": instrument.asset_class.value,
        },
    )


def order_intent_to_order(
    intent: OrderIntent,
    trader_id: TraderId,
    strategy_id: StrategyId,
    nautilus_instrument: CurrencyPair,
    ts_init_ns: int,
) -> MarketOrder | LimitOrder | StopMarketOrder | StopLimitOrder:
    """Map the canonical ``OrderIntent`` to a native Nautilus order.

    ``order_intent_id`` becomes the ``ClientOrderId`` — the idempotency key is
    identical for BACKTEST, PAPER and LIVE (INV-2).
    """
    instrument_id = nautilus_instrument.id
    client_order_id = ClientOrderId(str(intent.order_intent_id))
    order_side = _SIDE_MAP[intent.side]
    quantity = Quantity(intent.quantity, nautilus_instrument.size_precision)
    if quantity.as_decimal() != intent.quantity:
        raise ValueError(
            f"quantity {intent.quantity} is not representable with the instrument "
            f"size precision {nautilus_instrument.size_precision}"
        )
    time_in_force = _TIF_MAP[intent.time_in_force]
    # Nautilus requires a v4 init_id. It never enters any deterministic output
    # (event ordering is by ts_event; test_determinism verifies two runs hash
    # identically), so a random value is safe here — do not replace with a
    # non-v4 UUID: UUID4.from_str fails its version check.
    init_id = UUID4.from_str(str(_random_uuid4()))

    if intent.order_type is OrderType.MARKET:
        return MarketOrder(
            trader_id=trader_id,
            strategy_id=strategy_id,
            instrument_id=instrument_id,
            client_order_id=client_order_id,
            order_side=order_side,
            quantity=quantity,
            init_id=init_id,
            ts_init=ts_init_ns,
            time_in_force=time_in_force,
        )
    if intent.price is None:
        raise ValueError("LIMIT/STOP/STOP_LIMIT orders require a price")
    price = Price.from_str(str(intent.price))
    if intent.order_type is OrderType.LIMIT:
        return LimitOrder(
            trader_id=trader_id,
            strategy_id=strategy_id,
            instrument_id=instrument_id,
            client_order_id=client_order_id,
            order_side=order_side,
            quantity=quantity,
            price=price,
            init_id=init_id,
            ts_init=ts_init_ns,
            time_in_force=time_in_force,
        )
    if intent.order_type is OrderType.STOP:
        return StopMarketOrder(
            trader_id=trader_id,
            strategy_id=strategy_id,
            instrument_id=instrument_id,
            client_order_id=client_order_id,
            order_side=order_side,
            quantity=quantity,
            trigger_price=price,
            trigger_type=TriggerType.DEFAULT,
            init_id=init_id,
            ts_init=ts_init_ns,
            time_in_force=time_in_force,
        )
    if intent.stop_loss is None:
        raise ValueError("STOP_LIMIT orders require stop_loss as the trigger price")
    trigger_price = Price.from_str(str(intent.stop_loss))
    return StopLimitOrder(
        trader_id=trader_id,
        strategy_id=strategy_id,
        instrument_id=instrument_id,
        client_order_id=client_order_id,
        order_side=order_side,
        quantity=quantity,
        price=price,
        trigger_price=trigger_price,
        trigger_type=TriggerType.DEFAULT,
        init_id=init_id,
        ts_init=ts_init_ns,
        time_in_force=time_in_force,
    )


def report_from_order_submitted(
    event: OrderSubmitted, intent: OrderIntent, sequence: int, venue_name: str
) -> ExecutionReport:
    report_time = _to_utc(event.ts_event)
    return ExecutionReport(
        execution_report_id=uuid5(REPORT_NS, f"{intent.order_intent_id}:{sequence}"),
        order_intent_id=intent.order_intent_id,
        venue=venue_name,
        status=ExecutionState.SUBMITTED,
        report_time=report_time,
        sequence=sequence,
        produced_at=report_time,
        provenance=provenance(report_time),
    )


def report_from_order_accepted(
    event: OrderAccepted, intent: OrderIntent, sequence: int, venue_name: str
) -> ExecutionReport:
    report_time = _to_utc(event.ts_event)
    return ExecutionReport(
        execution_report_id=uuid5(REPORT_NS, f"{intent.order_intent_id}:{sequence}"),
        order_intent_id=intent.order_intent_id,
        venue=venue_name,
        venue_order_id=str(event.venue_order_id),
        status=ExecutionState.ACKNOWLEDGED,
        report_time=report_time,
        sequence=sequence,
        produced_at=report_time,
        provenance=provenance(report_time),
    )


def report_from_order_rejected(
    event: OrderRejected, intent: OrderIntent, sequence: int, venue_name: str
) -> ExecutionReport:
    report_time = _to_utc(event.ts_event)
    return ExecutionReport(
        execution_report_id=uuid5(REPORT_NS, f"{intent.order_intent_id}:{sequence}"),
        order_intent_id=intent.order_intent_id,
        venue=venue_name,
        status=ExecutionState.REJECTED,
        reject_reason=event.reason,
        report_time=report_time,
        sequence=sequence,
        produced_at=report_time,
        provenance=provenance(report_time),
    )


def report_from_order_denied(
    event: OrderDenied, intent: OrderIntent, sequence: int, venue_name: str
) -> ExecutionReport:
    report_time = _to_utc(event.ts_event)
    return ExecutionReport(
        execution_report_id=uuid5(REPORT_NS, f"{intent.order_intent_id}:{sequence}"),
        order_intent_id=intent.order_intent_id,
        venue=venue_name,
        status=ExecutionState.REJECTED,
        reject_reason=event.reason,
        report_time=report_time,
        sequence=sequence,
        produced_at=report_time,
        provenance=provenance(report_time),
    )


def report_from_order_filled(
    event: OrderFilled,
    intent: OrderIntent,
    sequence: int,
    venue_name: str,
    filled_total: Decimal,
) -> ExecutionReport:
    report_time = _to_utc(event.ts_event)
    status = (
        ExecutionState.FILLED if filled_total >= intent.quantity else ExecutionState.PARTIAL_FILL
    )
    return ExecutionReport(
        execution_report_id=uuid5(REPORT_NS, f"{intent.order_intent_id}:{sequence}"),
        order_intent_id=intent.order_intent_id,
        venue=venue_name,
        venue_order_id=str(event.venue_order_id),
        status=status,
        filled_quantity=event.last_qty.as_decimal(),
        average_fill_price=event.last_px.as_decimal(),
        commission=event.commission.as_decimal(),
        report_time=report_time,
        sequence=sequence,
        produced_at=report_time,
        provenance=provenance(report_time),
    )


def snapshot_from_position_event(
    event: PositionOpened | PositionChanged,
    mark_price: Decimal | None,
    unrealized_pnl: Decimal | None,
) -> PositionSnapshot:
    """Map a Nautilus position event to a domain ``PositionSnapshot``."""
    if event.side is NPositionSide.LONG:
        side = PositionSide.LONG
    elif event.side is NPositionSide.SHORT:
        side = PositionSide.SHORT
    else:
        raise ValueError("FLAT is not a position snapshot")
    as_of = _to_utc(event.ts_event)
    return PositionSnapshot(
        position_id=str(event.position_id),
        account_id=str(event.account_id),
        strategy_id=str(event.strategy_id),
        instrument_id=event.instrument_id.symbol.value,
        side=side,
        quantity=event.quantity.as_decimal(),
        average_entry_price=_decimal(event.avg_px_open),
        mark_price=mark_price,
        unrealized_pnl=unrealized_pnl,
        as_of=as_of,
        produced_at=as_of,
        provenance=provenance(as_of),
    )


def trade_outcome_from_position_closed(
    event: PositionClosed,
    order_intent_ids: list[str],
    costs: Decimal,
    slippage_total: Decimal,
    exit_reason: str,
    quantity: Decimal,
) -> TradeOutcome:
    """Map a Nautilus ``PositionClosed`` to a domain ``TradeOutcome``.

    ``event.quantity`` is the *remaining* quantity (0 at close); the traded
    quantity comes from the ledger's last known position size.
    """
    direction = SignalDirection.LONG if event.entry is NOrderSide.BUY else SignalDirection.SHORT
    opened_at = _to_utc(event.ts_opened)
    closed_at = _to_utc(event.ts_closed)
    return TradeOutcome(
        trade_id=uuid5(TRADE_NS, str(event.position_id)),
        position_id=str(event.position_id),
        order_intent_ids=order_intent_ids,
        instrument_id=event.instrument_id.symbol.value,
        direction=direction,
        quantity=quantity,
        entry_price=_decimal(event.avg_px_open),
        exit_price=_decimal(event.avg_px_close),
        # Nautilus realized_pnl is net of commissions; the domain contract keeps
        # realized_pnl gross with costs reported separately (net = realized - costs).
        realized_pnl=event.realized_pnl.as_decimal() + costs,
        costs=costs,
        slippage_total=slippage_total,
        holding_seconds=event.duration_ns // 1_000_000_000,
        opened_at=opened_at,
        closed_at=closed_at,
        exit_reason=exit_reason,
        produced_at=closed_at,
        provenance=provenance(closed_at),
    )
