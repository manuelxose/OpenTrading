"""The Nautilus-side strategy that routes canonical ``OrderIntent``s.

``NautilusRouterStrategy`` lives *inside* the Nautilus engine and is the venue's
execution gateway:

- every bar is wrapped in a point-in-time ``StrategyContext`` and offered to the
  domain strategy;
- returned ``OrderIntent``s pass the deterministic rejection simulator, then are
  mapped to native Nautilus orders and submitted;
- every Nautilus order/position event is mapped back into domain
  ``ExecutionReport`` / ``PositionSnapshot`` / ``TradeOutcome`` objects.

The same router (minus the virtual-clock specifics) serves PAPER and LIVE, keeping
one code path for all modes (INV-2, ADR-0007).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid5

from core.domain.enums import ExecutionState
from core.schemas import ExecutionReport, OrderIntent
from core.schemas.base import Provenance
from nautilus_trader.core.datetime import unix_nanos_to_dt
from nautilus_trader.model.data import Bar, QuoteTick
from nautilus_trader.model.enums import OrderSide as NOrderSide
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
from nautilus_trader.model.identifiers import TraderId
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.trading.strategy import Strategy

from adapters.nautilus.config import BacktestConfig
from adapters.nautilus.dataset import Dataset
from adapters.nautilus.ledger import PositionLedger
from adapters.nautilus.mapping import (
    REPORT_NS,
    order_intent_to_order,
    report_from_order_accepted,
    report_from_order_denied,
    report_from_order_filled,
    report_from_order_rejected,
    report_from_order_submitted,
)
from adapters.nautilus.models import ConfigurableSlippageFillModel
from adapters.nautilus.rejection import OrderRejectionSim
from adapters.nautilus.strategy import DomainStrategy, StrategyContext

__all__ = ["NautilusRouterStrategy"]

_PRODUCER = "adapters.nautilus.router"


class NautilusRouterStrategy(Strategy):  # type: ignore[misc]
    """Venue-side gateway between domain strategies and the Nautilus engine."""

    def __init__(
        self,
        config: BacktestConfig,
        domain_strategy: DomainStrategy,
        ledger: PositionLedger,
        dataset: Dataset,
        nautilus_instrument: CurrencyPair,
        fill_model: ConfigurableSlippageFillModel,
    ) -> None:
        super().__init__(StrategyConfig(strategy_id="ROUTER-001", order_id_tag="001"))
        self._config = config
        self._domain_strategy = domain_strategy
        self._ledger = ledger
        self._dataset = dataset
        self._nautilus_instrument = nautilus_instrument
        self._fill_model = fill_model
        self._rejection = OrderRejectionSim(config.rejection, config.seed, config.instrument)
        self._rejection.set_session(dataset.start_time, dataset.end_time)
        self._intent_by_client: dict[str, OrderIntent] = {}
        self._filled_by_client: dict[str, Decimal] = {}
        self._reports: list[ExecutionReport] = []
        self._equity_points: list[tuple[datetime, Decimal]] = []
        self._report_seq = 0
        self._bars_delivered = 0
        self._last_bar_ts_ns = dataset.bars[-1].ts_event if dataset.bars else 0
        self.account_id: str | None = None

    # ── lifecycle ─────────────────────────────────────────────────────────────
    def on_start(self) -> None:
        if self._dataset.bars:
            bar_type = self._dataset.bars[0].bar_type
            self.subscribe_bars(bar_type)
            self.subscribe_quote_ticks(bar_type.instrument_id)

    # ── market data ───────────────────────────────────────────────────────────
    def on_quote_tick(self, tick: QuoteTick) -> None:
        self._ledger.on_quote(
            tick.instrument_id.symbol.value,
            tick.bid_price.as_decimal(),
            tick.ask_price.as_decimal(),
        )

    def on_bar(self, bar: Bar) -> None:
        ts = unix_nanos_to_dt(bar.ts_event)
        self._bars_delivered += 1
        self._equity_points.append((ts, self._ledger.equity()))
        instrument_id = bar.bar_type.instrument_id.symbol.value
        quote = self._ledger.last_quote(instrument_id)
        last_bid = quote[0] if quote else None
        last_ask = quote[1] if quote else None
        bars_remaining = max(0, len(self._dataset.bars) - self._bars_delivered) + 1
        ctx = StrategyContext(
            instrument_id=instrument_id,
            as_of=ts,
            open_=bar.open.as_decimal(),
            high=bar.high.as_decimal(),
            low=bar.low.as_decimal(),
            close=bar.close.as_decimal(),
            volume=bar.volume.as_decimal(),
            position=self._ledger.current_position(instrument_id),
            last_bid=last_bid,
            last_ask=last_ask,
            is_last_bar=bar.ts_event >= self._last_bar_ts_ns,
            bars_remaining=bars_remaining,
        )
        for intent in self._domain_strategy.on_bar(ctx):
            self._route_intent(intent, ts)

    # ── order lifecycle → ExecutionReport ─────────────────────────────────────
    def on_order_submitted(self, event: OrderSubmitted) -> None:
        if self.account_id is None:
            self.account_id = str(event.account_id)
        intent = self._intent_by_client.get(event.client_order_id.value)
        if intent is not None:
            self._emit(
                report_from_order_submitted(event, intent, self._next_seq(), self.venue_name())
            )

    def on_order_accepted(self, event: OrderAccepted) -> None:
        if self.account_id is None:
            self.account_id = str(event.account_id)
        intent = self._intent_by_client.get(event.client_order_id.value)
        if intent is not None:
            self._emit(
                report_from_order_accepted(event, intent, self._next_seq(), self.venue_name())
            )

    def on_order_rejected(self, event: OrderRejected) -> None:
        intent = self._intent_by_client.get(event.client_order_id.value)
        if intent is not None:
            self._emit(
                report_from_order_rejected(event, intent, self._next_seq(), self.venue_name())
            )

    def on_order_denied(self, event: OrderDenied) -> None:
        intent = self._intent_by_client.get(event.client_order_id.value)
        if intent is not None:
            self._emit(report_from_order_denied(event, intent, self._next_seq(), self.venue_name()))

    def on_order_filled(self, event: OrderFilled) -> None:
        intent = self._intent_by_client.get(event.client_order_id.value)
        if intent is None:
            return
        filled = self._filled_by_client.get(event.client_order_id.value, Decimal("0"))
        filled += event.last_qty.as_decimal()
        self._filled_by_client[event.client_order_id.value] = filled
        slippage = self._slippage_for(event)
        self._ledger.on_fill(event, str(intent.order_intent_id), slippage)
        self._emit(
            report_from_order_filled(event, intent, self._next_seq(), self.venue_name(), filled)
        )

    def _slippage_for(self, event: OrderFilled) -> Decimal:
        """Adverse price distance vs the quote the fill simulation used."""
        theoretical: tuple[NOrderSide, Decimal, Decimal] | None = self._fill_model.theoretical(
            event.client_order_id.value
        )
        if theoretical is None:
            return Decimal("0")
        _side, best_bid, best_ask = theoretical
        qty: Decimal = event.last_qty.as_decimal()
        px: Decimal = event.last_px.as_decimal()
        if event.order_side is NOrderSide.BUY:
            return max(Decimal("0"), px - best_ask) * qty
        return max(Decimal("0"), best_bid - px) * qty

    # ── position lifecycle → PositionSnapshot / TradeOutcome ──────────────────
    def on_position_opened(self, event: PositionOpened) -> None:
        self._ledger.on_position_opened(event)

    def on_position_changed(self, event: PositionChanged) -> None:
        self._ledger.on_position_changed(event)

    def on_position_closed(self, event: PositionClosed) -> None:
        self._ledger.on_position_closed(event)

    # ── internals ─────────────────────────────────────────────────────────────
    def _route_intent(self, intent: OrderIntent, ts: datetime) -> None:
        instrument_id = intent.instrument_id
        quote = self._ledger.last_quote(instrument_id)
        last_bid = quote[0] if quote else None
        last_ask = quote[1] if quote else None
        reason = self._rejection.reason(intent, ts, last_bid, last_ask)
        if reason is not None:
            seq = self._next_seq()
            self._emit(
                ExecutionReport(
                    execution_report_id=uuid5(REPORT_NS, f"{intent.order_intent_id}:{seq}"),
                    order_intent_id=intent.order_intent_id,
                    venue=self.venue_name(),
                    status=ExecutionState.REJECTED,
                    reject_reason=reason,
                    report_time=ts,
                    sequence=seq,
                    produced_at=ts,
                    provenance=Provenance(producer=_PRODUCER, produced_at=ts),
                )
            )
            return
        order = order_intent_to_order(
            intent,
            TraderId(self._config.trader_id),
            self.id,
            self._nautilus_instrument,
            self.clock.timestamp_ns(),
        )
        self._intent_by_client[order.client_order_id.value] = intent
        self.submit_order(order)

    def venue_name(self) -> str:
        return self._config.venue_name

    def _next_seq(self) -> int:
        self._report_seq += 1
        return self._report_seq

    def _emit(self, report: ExecutionReport) -> None:
        self._reports.append(report)

    # ── results accessors ─────────────────────────────────────────────────────
    @property
    def execution_reports(self) -> list[ExecutionReport]:
        return list(self._reports)

    @property
    def equity_points(self) -> list[tuple[datetime, Decimal]]:
        return list(self._equity_points)
