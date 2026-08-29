"""Deterministic simulated broker for the MT4 emulator (Phase 6, ADR-0020).

The emulator runs the EA-side defense-in-depth validations frozen in §8 / INV-5
(trading enabled, symbol whitelist, lot limits/step, spread limit, free margin,
quote freshness, market open, stop/freeze level, duplicate intent, MagicNumber,
command expiry) against this broker. The broker itself is a deterministic venue:
seeded random-walk quotes, exact Decimal arithmetic, no wall-clock reads.

Nothing here needs MetaTrader — this is what lets the Core exercise the full
execution lifecycle against an emulator (Phase 6 DoD).
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from uuid import UUID

from core.clock.clocks import Clock
from core.domain.enums import OrderSide, OrderType, PositionSide
from core.schemas.base import Provenance, ensure_utc
from core.schemas.trading import PositionSnapshot as CanonicalPositionSnapshot
from pydantic import BaseModel, ConfigDict, Field, model_validator

from adapters.mt4.errors import Mt4ErrorCode, ProtocolErrorDetail
from adapters.mt4.protocol import (
    AccountSnapshotEvent,
    AccountState,
    CancelOrderCommand,
    CommandMessage,
    FillEvent,
    ModifyOrderCommand,
    OrderAck,
    PartialFillEvent,
    PositionSnapshotEvent,
    SubmitOrderCommand,
    VenuePosition,
    WireMessage,
)

__all__ = [
    "BrokerConfig",
    "BrokerOutcome",
    "SimulatedBroker",
    "SymbolSpec",
    "WorkingOrder",
    "strategy_magic",
]

#: Placeholder frame fields filled in by the emulator when framing events.
_PLACEHOLDER_ID = UUID(int=0)


def strategy_magic(strategy_id: str) -> int:
    """Deterministic MagicNumber derived from strategy_id (same on both sides)."""
    digest = hashlib.sha256(strategy_id.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF


def _quote(qty: Decimal, step: Decimal) -> Decimal:
    """Round qty DOWN to a multiple of lot_step (broker lot rounding)."""
    return (qty / step).to_integral_value(rounding=ROUND_HALF_UP) * step


class SymbolSpec(BaseModel):
    """Broker-side symbol constraints the EA enforces before sending orders."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    min_lot: Decimal = Field(default=Decimal("0.01"), gt=0)
    max_lot: Decimal = Field(default=Decimal("100"), gt=0)
    lot_step: Decimal = Field(default=Decimal("0.01"), gt=0)
    contract_size: Decimal = Field(default=Decimal("100000"), gt=0)
    spread: Decimal = Field(default=Decimal("0.00012"), ge=0)
    max_spread: Decimal = Field(default=Decimal("0.0003"), gt=0)
    stop_level: Decimal = Field(default=Decimal("0.0005"), ge=0)
    freeze_level: Decimal = Field(default=Decimal("0"), ge=0)
    initial_mid: Decimal = Field(default=Decimal("1.08000"), gt=0)
    vol_per_step: Decimal = Field(default=Decimal("0.00005"), ge=0)
    digits: int = Field(default=5, ge=0, le=8)


class BrokerConfig(BaseModel):
    """Configuration of the simulated venue."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    account_id: str = Field(default="DEMO-0001", min_length=1)
    is_demo: bool = True
    currency: str = Field(default="USD", min_length=3, max_length=3)
    balance: Decimal = Field(default=Decimal("100000"), gt=0)
    leverage: Decimal = Field(default=Decimal("100"), gt=0)
    symbols: dict[str, SymbolSpec] = Field(default_factory=dict)
    trading_enabled: bool = True
    market_open: bool = True
    max_quote_age_seconds: float = Field(default=5.0, gt=0)
    partial_fill_ratio: Decimal = Field(default=Decimal("1"), gt=0, le=1)
    commission_per_lot: Decimal = Field(default=Decimal("0"), ge=0)
    magic_whitelist: tuple[int, ...] = ()

    @model_validator(mode="after")
    def _default_symbols(self) -> BrokerConfig:
        if not self.symbols:
            object.__setattr__(self, "symbols", {"EURUSD": SymbolSpec()})
        return self


@dataclass
class WorkingOrder:
    """A resting order at the venue (LIMIT/STOP, or unfilled MARKET remainder)."""

    venue_order_id: str
    order_intent_id: UUID
    strategy_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: Decimal
    remaining: Decimal
    price: Decimal | None
    stop_loss: Decimal | None
    take_profit: Decimal | None
    magic: int
    ref_price: Decimal
    max_slippage: Decimal


@dataclass
class BrokerOutcome:
    """Result of processing one command: a reply and/or async events."""

    ack: OrderAck | None = None
    reject: ProtocolErrorDetail | None = None
    events: list[WireMessage] = field(default_factory=list)


class QuoteEngine:
    """Seeded random-walk quote generator — deterministic per (seed, symbol)."""

    def __init__(self, seed: int, symbols: dict[str, SymbolSpec]) -> None:
        self._seed = seed
        self._symbols = symbols
        self._rngs: dict[str, random.Random] = {}
        self._mids: dict[str, Decimal] = {}
        self._last_quote_at: dict[str, datetime] = {}
        for symbol, spec in symbols.items():
            self._rngs[symbol] = random.Random(f"{seed}:{symbol}")
            self._mids[symbol] = spec.initial_mid
            self._last_quote_at[symbol] = datetime.min.replace(tzinfo=UTC)

    def step(self, symbol: str, now: datetime) -> None:
        """Advance one deterministic random-walk step for ``symbol``."""
        spec = self._symbols[symbol]
        rng = self._rngs[symbol]
        shift = Decimal(str(rng.uniform(-1.0, 1.0))) * spec.vol_per_step
        self._mids[symbol] = (self._mids[symbol] + shift).quantize(
            Decimal("1").scaleb(-spec.digits)
        )
        self._last_quote_at[symbol] = ensure_utc(now)

    def bid(self, symbol: str) -> Decimal:
        return self._mids[symbol] - self._symbols[symbol].spread / 2

    def ask(self, symbol: str) -> Decimal:
        return self._mids[symbol] + self._symbols[symbol].spread / 2

    def age(self, symbol: str, now: datetime) -> float:
        last = self._last_quote_at[symbol]
        if last == datetime.min.replace(tzinfo=UTC):
            return float("inf")
        return (ensure_utc(now) - last).total_seconds()


class SimulatedBroker:
    """The venue behind the emulator. Deterministic; no I/O; no MetaTrader."""

    def __init__(
        self,
        clock: Clock,
        config: BrokerConfig,
        seed: int = 42,
    ) -> None:
        self._clock = clock
        self._config = config
        self._quotes = QuoteEngine(seed, config.symbols)
        for symbol in config.symbols:
            self._quotes.step(symbol, self._clock.now())
        self._positions: dict[str, VenuePosition] = {}
        self._working: dict[str, WorkingOrder] = {}
        self._counter = 0
        self._balance = config.balance
        self._realized = Decimal("0")

    # ── State accessors ───────────────────────────────────────────────────
    @property
    def trading_enabled(self) -> bool:
        return self._config.trading_enabled

    def set_trading_enabled(self, value: bool) -> None:
        object.__setattr__(self._config, "trading_enabled", value)

    def account_state(self, now: datetime | None = None) -> AccountState:
        now = now or self._clock.now()
        margin = sum(
            (
                (p.position.quantity * self._spec(p.position.instrument_id).contract_size)
                / self._config.leverage
                for p in self._positions.values()
            ),
            Decimal("0"),
        )
        return AccountState(
            account_id=self._config.account_id,
            is_demo=self._config.is_demo,
            currency=self._config.currency,
            balance=self._balance,
            equity=self._balance + self._realized,
            margin=margin,
            free_margin=self._balance + self._realized - margin,
            as_of=ensure_utc(now),
        )

    def positions(self, now: datetime | None = None) -> tuple[VenuePosition, ...]:
        return tuple(self._positions.values())

    def open_order_intent_ids(self) -> tuple[UUID, ...]:
        return tuple(o.order_intent_id for o in self._working.values())

    def open_manual_position(
        self, position: CanonicalPositionSnapshot, *, magic: int = 0
    ) -> VenuePosition:
        """Simulate a human placing a trade directly at MT4.

        The Core never sent this position, so reconciliation must flag it as an
        unexpected broker position (INV-6) and escalate to SAFE_MODE.
        """
        venue_position = VenuePosition(
            venue_position_id=position.position_id,
            magic=magic,
            position=position,
        )
        self._positions[position.position_id] = venue_position
        return venue_position

    def symbols(self) -> tuple[str, ...]:
        return tuple(self._config.symbols)

    def bid(self, symbol: str) -> Decimal:
        return self._quotes.bid(symbol)

    def ask(self, symbol: str) -> Decimal:
        return self._quotes.ask(symbol)

    def quote_age(self, symbol: str, now: datetime) -> float:
        return self._quotes.age(symbol, now)

    # ── Periodic advance (quote steps + resting-order matching) ──────────
    def advance(self, now: datetime | None = None) -> list[WireMessage]:
        """Step quotes and match resting orders. Returns generated events."""
        now = ensure_utc(now or self._clock.now())
        events: list[WireMessage] = []
        for symbol in self._config.symbols:
            self._quotes.step(symbol, now)
        for venue_order_id in list(self._working):
            order = self._working[venue_order_id]
            if self._is_touched(order):
                events.extend(self._fill_order(order, now, reason="quote_touch"))
        return events

    # ── Commands ──────────────────────────────────────────────────────────
    def process_submit(
        self, command: SubmitOrderCommand, now: datetime | None = None
    ) -> BrokerOutcome:
        now = ensure_utc(now or self._clock.now())
        assert command.order_intent_id is not None and command.symbol is not None
        assert command.side is not None and command.quantity is not None
        assert command.order_type is not None

        reject = self._venue_checks(command, now)
        if reject is not None:
            return BrokerOutcome(reject=reject)

        venue_order_id = self._next_id("vo")
        magic = strategy_magic(command.strategy_id)
        assert command.side is not None
        order = WorkingOrder(
            venue_order_id=venue_order_id,
            order_intent_id=command.order_intent_id,
            strategy_id=command.strategy_id,
            symbol=command.symbol,
            side=command.side,
            order_type=command.order_type,
            quantity=command.quantity,
            remaining=command.quantity,
            price=command.price,
            stop_loss=command.stop_loss,
            take_profit=command.take_profit,
            magic=magic,
            ref_price=self._quotes.ask(command.symbol)
            if command.side is OrderSide.BUY
            else self._quotes.bid(command.symbol),
            max_slippage=command.max_slippage,
        )
        self._working[venue_order_id] = order
        events: list[WireMessage] = []

        if command.order_type is OrderType.MARKET:
            events.extend(self._fill_order(order, now, reason="market_submit"))

        ack_status: Literal["FILLED", "SUBMITTED"] = (
            "FILLED" if order.remaining == 0 else "SUBMITTED"
        )
        ack = OrderAck(
            message_id=_PLACEHOLDER_ID,
            timestamp=now,
            sequence=0,
            order_intent_id=command.order_intent_id,
            status=ack_status,
            venue_order_id=venue_order_id,
        )
        return BrokerOutcome(ack=ack, events=events)

    def process_cancel(
        self, command: CancelOrderCommand, now: datetime | None = None
    ) -> BrokerOutcome:
        now = ensure_utc(now or self._clock.now())
        assert command.order_intent_id is not None
        order = self._working_by_intent(command.order_intent_id)
        if order is None:
            if self._positions_by_intent(command.order_intent_id):
                return BrokerOutcome(
                    reject=self._reject(
                        command, Mt4ErrorCode.ORDER_NOT_ACTIVE, now, "order already filled"
                    )
                )
            return BrokerOutcome(
                reject=self._reject(command, Mt4ErrorCode.UNKNOWN_ORDER, now, "no such order")
            )
        if order.remaining <= 0:
            return BrokerOutcome(
                reject=self._reject(
                    command, Mt4ErrorCode.ORDER_NOT_ACTIVE, now, "order already filled"
                )
            )
        del self._working[order.venue_order_id]
        ack = OrderAck(
            message_id=_PLACEHOLDER_ID,
            timestamp=now,
            sequence=0,
            order_intent_id=command.order_intent_id,
            status="CANCELLED",
            venue_order_id=order.venue_order_id,
            message=command.reason,
        )
        return BrokerOutcome(ack=ack)

    def process_modify(
        self, command: ModifyOrderCommand, now: datetime | None = None
    ) -> BrokerOutcome:
        now = ensure_utc(now or self._clock.now())
        assert command.order_intent_id is not None
        order = self._working_by_intent(command.order_intent_id)
        if order is None:
            return BrokerOutcome(
                reject=self._reject(command, Mt4ErrorCode.UNKNOWN_ORDER, now, "no such order")
            )
        if order.remaining <= 0:
            return BrokerOutcome(
                reject=self._reject(
                    command, Mt4ErrorCode.ORDER_NOT_ACTIVE, now, "order already filled"
                )
            )
        new_price = command.new_price if command.new_price is not None else order.price
        new_sl = command.new_stop_loss if command.new_stop_loss is not None else order.stop_loss
        new_tp = (
            command.new_take_profit if command.new_take_profit is not None else order.take_profit
        )
        spec = self._config.symbols[order.symbol]
        if (
            command.new_price is not None
            and order.price is not None
            and abs(command.new_price - order.price) < spec.freeze_level
        ):
            return BrokerOutcome(
                reject=self._reject(
                    command,
                    Mt4ErrorCode.STOP_LEVEL_VIOLATION,
                    now,
                    "price move within freeze_level",
                )
            )
        stop_reject = self._stop_level_check(
            order.symbol, order.side, new_price, new_sl, new_tp, now
        )
        if stop_reject is not None:
            return BrokerOutcome(reject=stop_reject)
        object.__setattr__(order, "price", new_price)
        object.__setattr__(order, "stop_loss", new_sl)
        object.__setattr__(order, "take_profit", new_tp)
        ack = OrderAck(
            message_id=_PLACEHOLDER_ID,
            timestamp=now,
            sequence=0,
            order_intent_id=command.order_intent_id,
            status="MODIFIED",
            venue_order_id=order.venue_order_id,
        )
        return BrokerOutcome(ack=ack)

    # ── Validations (EA defense-in-depth, INV-5 §8) ──────────────────────
    def _venue_checks(
        self, command: SubmitOrderCommand, now: datetime
    ) -> ProtocolErrorDetail | None:
        if not self._config.trading_enabled:
            return self._reject(command, Mt4ErrorCode.TRADING_DISABLED, now, "trading disabled")
        if not self._config.market_open:
            return self._reject(command, Mt4ErrorCode.MARKET_CLOSED, now, "market closed")
        assert command.symbol is not None
        spec = self._config.symbols.get(command.symbol)
        if spec is None:
            return self._reject(
                command, Mt4ErrorCode.SYMBOL_NOT_ALLOWED, now, "symbol not whitelisted"
            )
        assert command.quantity is not None
        if command.quantity < spec.min_lot:
            return self._reject(command, Mt4ErrorCode.LOT_LIMIT_EXCEEDED, now, "below min_lot")
        if command.quantity > spec.max_lot:
            return self._reject(command, Mt4ErrorCode.LOT_LIMIT_EXCEEDED, now, "above max_lot")
        if command.quantity % spec.lot_step != 0:
            return self._reject(
                command, Mt4ErrorCode.LOT_STEP_INVALID, now, "not a lot_step multiple"
            )
        if self._quotes.age(command.symbol, now) > self._config.max_quote_age_seconds:
            return self._reject(command, Mt4ErrorCode.STALE_QUOTES, now, "quotes too old")
        if self._quotes.ask(command.symbol) - self._quotes.bid(command.symbol) > spec.max_spread:
            return self._reject(command, Mt4ErrorCode.SPREAD_TOO_HIGH, now, "spread over limit")
        assert command.side is not None
        stop_reject = self._stop_level_check(
            command.symbol, command.side, command.price, command.stop_loss, command.take_profit, now
        )
        if stop_reject is not None:
            return stop_reject
        assert command.quantity is not None
        required_margin = (
            command.quantity * spec.contract_size * self._quotes.ask(command.symbol)
        ) / self._config.leverage
        if required_margin > self.account_state(now).free_margin:
            return self._reject(
                command, Mt4ErrorCode.INSUFFICIENT_MARGIN, now, "free margin too low"
            )
        magic = strategy_magic(command.strategy_id)
        if self._config.magic_whitelist and magic not in self._config.magic_whitelist:
            return self._reject(
                command, Mt4ErrorCode.INVALID_MAGIC, now, "strategy magic not allowed"
            )
        return None

    def _stop_level_check(
        self,
        symbol: str,
        side: OrderSide,
        price: Decimal | None,
        stop_loss: Decimal | None,
        take_profit: Decimal | None,
        now: datetime,
    ) -> ProtocolErrorDetail | None:
        spec = self._config.symbols[symbol]
        reference = price if price is not None else self._quotes.ask(symbol)
        for name, value in (("stop_loss", stop_loss), ("take_profit", take_profit)):
            if value is None:
                continue
            distance = abs(reference - value)
            if side is OrderSide.BUY and name == "stop_loss" and value >= reference:
                return ProtocolErrorDetail.create(
                    Mt4ErrorCode.STOP_LEVEL_VIOLATION,
                    "buy stop_loss must be below price",
                    symbol=symbol,
                    now=now,
                )
            if side is OrderSide.BUY and name == "take_profit" and value <= reference:
                return ProtocolErrorDetail.create(
                    Mt4ErrorCode.STOP_LEVEL_VIOLATION,
                    "buy take_profit must be above price",
                    symbol=symbol,
                    now=now,
                )
            if side is OrderSide.SELL and name == "stop_loss" and value <= reference:
                return ProtocolErrorDetail.create(
                    Mt4ErrorCode.STOP_LEVEL_VIOLATION,
                    "sell stop_loss must be above price",
                    symbol=symbol,
                    now=now,
                )
            if side is OrderSide.SELL and name == "take_profit" and value >= reference:
                return ProtocolErrorDetail.create(
                    Mt4ErrorCode.STOP_LEVEL_VIOLATION,
                    "sell take_profit must be below price",
                    symbol=symbol,
                    now=now,
                )
            if distance < spec.stop_level:
                return ProtocolErrorDetail.create(
                    Mt4ErrorCode.STOP_LEVEL_VIOLATION,
                    f"{name} within stop_level {spec.stop_level}",
                    symbol=symbol,
                    now=now,
                )
        return None

    # ── Matching ──────────────────────────────────────────────────────────
    def _is_touched(self, order: WorkingOrder) -> bool:
        if order.order_type is OrderType.MARKET:
            return True  # a partially-filled MARKET remainder fills on the next quote
        if order.price is None:
            return False
        bid, ask = self._quotes.bid(order.symbol), self._quotes.ask(order.symbol)
        if order.order_type is OrderType.LIMIT:
            return ask <= order.price if order.side is OrderSide.BUY else bid >= order.price
        if order.order_type is OrderType.STOP:
            return ask >= order.price if order.side is OrderSide.BUY else bid <= order.price
        if order.order_type is OrderType.STOP_LIMIT:
            return ask >= order.price if order.side is OrderSide.BUY else bid <= order.price
        return False

    def _fill_order(self, order: WorkingOrder, now: datetime, *, reason: str) -> list[WireMessage]:
        fill_price = (
            self._quotes.ask(order.symbol)
            if order.side is OrderSide.BUY
            else self._quotes.bid(order.symbol)
        )
        slippage = fill_price - order.ref_price
        if order.side is OrderSide.SELL:
            slippage = -slippage
        if slippage > order.max_slippage:
            # OrderSend(slippage=max_slippage) refused the fill; order stays resting.
            return []
        if order.order_type is OrderType.MARKET and order.remaining == order.quantity:
            partial_ratio = self._config.partial_fill_ratio
        else:
            partial_ratio = Decimal("1")
        fill_qty = (
            order.remaining
            if partial_ratio >= 1
            else (order.remaining * partial_ratio).quantize(Decimal("0.000001"))
        )
        spec = self._config.symbols[order.symbol]
        fill_qty = _quote(fill_qty, spec.lot_step)
        if fill_qty <= 0:
            return []
        order.remaining -= fill_qty
        events: list[WireMessage] = []
        commission = fill_qty * self._config.commission_per_lot
        base_event: PartialFillEvent | FillEvent
        if order.remaining > 0:
            base_event = PartialFillEvent(
                message_id=_PLACEHOLDER_ID,
                timestamp=now,
                sequence=0,
                order_intent_id=order.order_intent_id,
                venue_order_id=order.venue_order_id,
                filled_quantity=fill_qty,
                remaining_quantity=order.remaining,
                average_fill_price=fill_price,
                commission=commission,
                slippage=slippage,
                symbol=order.symbol,
            )
        else:
            base_event = FillEvent(
                message_id=_PLACEHOLDER_ID,
                timestamp=now,
                sequence=0,
                order_intent_id=order.order_intent_id,
                venue_order_id=order.venue_order_id,
                filled_quantity=fill_qty,
                average_fill_price=fill_price,
                commission=commission,
                slippage=slippage,
                symbol=order.symbol,
                side=order.side,
            )
            del self._working[order.venue_order_id]
            self._realized -= commission
        events.append(base_event)
        events.append(self._position_event(order, fill_qty, fill_price, now))
        events.append(self._account_event(now))
        return events

    def _position_event(
        self, order: WorkingOrder, fill_qty: Decimal, price: Decimal, now: datetime
    ) -> WireMessage:
        """Net the fill into a position and emit a position_snapshot."""
        assert order.symbol is not None
        existing = self._positions_by_intent(order.order_intent_id)
        if existing is None:
            venue_position_id = self._next_id("pos")
            position = CanonicalPositionSnapshot(
                trace_id=order.order_intent_id,
                produced_at=now,
                provenance=Provenance(
                    producer="mt4-emulator",
                    produced_at=now,
                    source_ids={"order_intent_id": str(order.order_intent_id)},
                ),
                position_id=venue_position_id,
                account_id=self._config.account_id,
                strategy_id=order.strategy_id,
                instrument_id=order.symbol,
                side=PositionSide.LONG if order.side is OrderSide.BUY else PositionSide.SHORT,
                quantity=fill_qty,
                average_entry_price=price,
                mark_price=price,
                as_of=now,
            )
            self._positions[venue_position_id] = VenuePosition(
                venue_position_id=venue_position_id,
                magic=order.magic,
                position=position,
            )
        else:
            assert order.symbol is not None
            quantity = existing.position.quantity + fill_qty
            average = (
                (existing.position.average_entry_price * existing.position.quantity)
                + (price * fill_qty)
            ) / quantity
            position = existing.position.model_copy(
                update={"quantity": quantity, "average_entry_price": average, "as_of": now}
            )
            self._positions[existing.venue_position_id] = VenuePosition(
                venue_position_id=existing.venue_position_id,
                magic=existing.magic,
                position=position,
            )
        return PositionSnapshotEvent(
            message_id=_PLACEHOLDER_ID,
            timestamp=now,
            sequence=0,
            account_id=self._config.account_id,
            positions=tuple(self._positions.values()),
        )

    def _account_event(self, now: datetime) -> WireMessage:
        return AccountSnapshotEvent(
            message_id=_PLACEHOLDER_ID,
            timestamp=now,
            sequence=0,
            account=self.account_state(now),
        )

    # ── Helpers ───────────────────────────────────────────────────────────
    def _spec(self, symbol: str) -> SymbolSpec:
        return self._config.symbols[symbol]

    def _next_id(self, prefix: str) -> str:
        self._counter += 1
        return f"{prefix}-{self._counter}"

    def _working_by_intent(self, order_intent_id: UUID) -> WorkingOrder | None:
        for order in self._working.values():
            if order.order_intent_id == order_intent_id:
                return order
        return None

    def _positions_by_intent(self, order_intent_id: UUID) -> VenuePosition | None:
        for position in self._positions.values():
            if position.position.provenance.source_ids.get("order_intent_id") == str(
                order_intent_id
            ):
                return position
        return None

    def _reject(
        self,
        command: CommandMessage,
        code: Mt4ErrorCode,
        now: datetime,
        detail: str,
    ) -> ProtocolErrorDetail:
        return ProtocolErrorDetail.create(
            code,
            code.value.lower().replace("_", " "),
            detail=detail,
            trace_id=command.trace_id,
            order_intent_id=command.order_intent_id,
            symbol=command.symbol,
            sequence=command.sequence,
            now=now,
        )
