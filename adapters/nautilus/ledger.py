"""Domain-side position accounting that mirrors the Nautilus venue ledger.

Nautilus owns the authoritative simulated accounting inside the engine; this ledger
re-derives domain ``PositionSnapshot`` / ``TradeOutcome`` objects from the same
order/position event stream (never by peeking into Nautilus internals), and keeps
a cash balance per currency so end-of-run equity and drawdown are computable
deterministically (ADR-0007, INV-6 spirit: the two books must agree).

Scope: FX pairs quoted in the account currency (e.g. EURUSD in a USD account).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from core.domain.enums import OrderSide, PositionSide
from core.schemas import Instrument, PositionSnapshot, TradeOutcome
from nautilus_trader.core.datetime import unix_nanos_to_dt
from nautilus_trader.model.enums import OrderSide as NOrderSide
from nautilus_trader.model.enums import PositionSide as NPositionSide
from nautilus_trader.model.events import (
    OrderFilled,
    PositionChanged,
    PositionClosed,
    PositionOpened,
)

from adapters.nautilus.mapping import (
    snapshot_from_position_event,
    trade_outcome_from_position_closed,
)

__all__ = ["PositionLedger"]

_EXIT_REASON = "SIGNAL_EXIT"


@dataclass
class _OpenPosition:
    position_id: str
    account_id: str
    strategy_id: str
    instrument_id: str
    side: PositionSide
    quantity: Decimal
    avg_entry: Decimal
    opened_at: datetime
    last_snapshot: PositionSnapshot | None = None


class PositionLedger:
    """Cash balances + open positions, updated exclusively from venue events."""

    def __init__(
        self,
        instrument: Instrument,
        starting_balances: dict[str, Decimal],
        account_currency: str,
        fallback_mark: Decimal | None = None,
    ) -> None:
        if instrument.quote_currency != account_currency:
            raise NotImplementedError(
                "PositionLedger currently supports pairs quoted in the account currency"
            )
        if not instrument.base_currency:
            raise ValueError("instrument requires base_currency")
        self._instrument = instrument
        self._base = instrument.base_currency
        self._quote = account_currency
        self._fallback_mark = fallback_mark
        self._balances = dict(starting_balances)
        self._balances.setdefault(self._base, Decimal("0"))
        self._balances.setdefault(self._quote, Decimal("0"))
        self._open: dict[str, _OpenPosition] = {}
        self._last_quote: dict[str, tuple[Decimal, Decimal]] = {}
        self._intent_ids_by_key: dict[str, list[str]] = {}
        self._commission_by_key: dict[str, Decimal] = {}
        self._slippage_by_key: dict[str, Decimal] = {}
        self._snapshots: list[PositionSnapshot] = []
        self._outcomes: list[TradeOutcome] = []

    # ── market data mirror ────────────────────────────────────────────────────
    def on_quote(self, instrument_id: str, bid: Decimal, ask: Decimal) -> None:
        self._last_quote[instrument_id] = (bid, ask)

    def last_quote(self, instrument_id: str) -> tuple[Decimal, Decimal] | None:
        return self._last_quote.get(instrument_id)

    def mark(self, instrument_id: str) -> Decimal | None:
        quote = self._last_quote.get(instrument_id)
        if quote is not None:
            return (quote[0] + quote[1]) / 2
        return self._fallback_mark

    # ── event ingestion ───────────────────────────────────────────────────────
    def on_fill(self, event: OrderFilled, intent_id: str, slippage: Decimal) -> None:
        """Apply a fill to the cash book (spot FX settlement) and cost tracking."""
        qty = event.last_qty.as_decimal()
        px = event.last_px.as_decimal()
        commission = event.commission.as_decimal()
        side = OrderSide.BUY if event.order_side is NOrderSide.BUY else OrderSide.SELL
        if side is OrderSide.BUY:
            self._balances[self._base] += qty
            self._balances[self._quote] -= qty * px + commission
        else:
            self._balances[self._base] -= qty
            self._balances[self._quote] += qty * px - commission
        key = self._position_key(event)
        self._intent_ids_by_key.setdefault(key, []).append(intent_id)
        self._commission_by_key[key] = self._commission_by_key.get(key, Decimal("0")) + commission
        self._slippage_by_key[key] = self._slippage_by_key.get(key, Decimal("0")) + slippage

    def on_position_opened(self, event: PositionOpened) -> None:
        # Fill-driven accumulators are popped on close; the entry fill lands
        # before this event, so no reset here (NETTING reuses the position id).
        self._open[self._position_key(event)] = _OpenPosition(
            position_id=str(event.position_id),
            account_id=str(event.account_id),
            strategy_id=str(event.strategy_id),
            instrument_id=event.instrument_id.symbol.value,
            side=self._side(event.side),
            quantity=event.quantity.as_decimal(),
            avg_entry=Decimal(str(event.avg_px_open)),
            opened_at=unix_nanos_to_dt(event.ts_event),
        )
        self._record_snapshot(self._position_key(event), event)

    def on_position_changed(self, event: PositionChanged) -> None:
        key = self._position_key(event)
        position = self._open.get(key)
        if position is None:  # defensive: a change implies a prior open
            return
        position.quantity = event.quantity.as_decimal()
        position.avg_entry = Decimal(str(event.avg_px_open))
        self._record_snapshot(key, event)

    def on_position_closed(self, event: PositionClosed) -> TradeOutcome:
        key = self._position_key(event)
        position = self._open.pop(key, None)
        intent_ids = list(self._intent_ids_by_key.pop(key, []))
        costs = self._commission_by_key.pop(key, Decimal("0"))
        slippage = self._slippage_by_key.pop(key, Decimal("0"))
        quantity = (
            position.quantity
            if position is not None and position.quantity > 0
            else event.peak_qty.as_decimal()
        )
        outcome = trade_outcome_from_position_closed(
            event, intent_ids, costs, slippage, _EXIT_REASON, quantity
        )
        self._outcomes.append(outcome)
        return outcome

    # ── internals ─────────────────────────────────────────────────────────────
    @staticmethod
    def _side(side: NPositionSide) -> PositionSide:
        if side is NPositionSide.LONG:
            return PositionSide.LONG
        if side is NPositionSide.SHORT:
            return PositionSide.SHORT
        raise ValueError("a FLAT position cannot be tracked")

    def _position_key(self, event: object) -> str:
        position_id = getattr(event, "position_id", None)
        if position_id is not None:
            return str(position_id)
        instrument_id = getattr(event, "instrument_id", None)
        symbol = getattr(instrument_id, "symbol", None)
        return f"netting:{getattr(symbol, 'value', '')}"

    def _record_snapshot(self, key: str, event: PositionOpened | PositionChanged) -> None:
        position = self._open.get(key)
        if position is None:
            return
        mark = self.mark(position.instrument_id)
        unrealized = self._unrealized(position, mark)
        snapshot = snapshot_from_position_event(event, mark, unrealized)
        position.last_snapshot = snapshot
        self._snapshots.append(snapshot)

    def _unrealized(self, position: _OpenPosition, mark: Decimal | None) -> Decimal | None:
        if mark is None:
            return None
        signed = position.quantity if position.side is PositionSide.LONG else -position.quantity
        return signed * (mark - position.avg_entry)

    # ── run-end views ─────────────────────────────────────────────────────────
    def current_position(self, instrument_id: str) -> PositionSnapshot | None:
        for position in self._open.values():
            if position.instrument_id == instrument_id:
                return position.last_snapshot
        return None

    def open_positions(self) -> list[PositionSnapshot]:
        return [p.last_snapshot for p in self._open.values() if p.last_snapshot is not None]

    def balances(self) -> dict[str, Decimal]:
        return dict(self._balances)

    def equity(self) -> Decimal:
        """Account-currency equity: quote cash + base cash at mid + unrealized."""
        mark = self.mark(self._instrument.instrument_id)
        equity = self._balances[self._quote]
        if mark is not None:
            equity += self._balances[self._base] * mark
        for position in self._open.values():
            unrealized = self._unrealized(position, mark)
            if unrealized is not None:
                equity += unrealized
        return equity

    @property
    def snapshots(self) -> list[PositionSnapshot]:
        return list(self._snapshots)

    @property
    def outcomes(self) -> list[TradeOutcome]:
        return list(self._outcomes)
