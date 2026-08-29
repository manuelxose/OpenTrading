"""Nautilus paper execution venue (Phase 7, architecture §32 Fase 7).

PAPER mode runs the *same* Nautilus mapping, fill and fee models as BACKTEST
(INV-2: one code path), but one order at a time against the live
:class:`MarketSnapshot` instead of a historical dataset.

:class:`NautilusPaperExecutor.submit` builds a minimal single-purpose
``BacktestEngine`` whose market data is the snapshot's current bid/ask, submits
the canonical ``OrderIntent`` through the shared ``order_intent_to_order``
mapping, and returns the venue's :class:`ExecutionReport` sequence
(SUBMITTED → ACKNOWLEDGED → FILLED / REJECTED). Costs (slippage, commission)
come from the same seeded models as backtests.

The executor never holds position state across orders — position accounting is
owned by the worker's :class:`apps.worker.ledger.PaperLedger`, which is the
authoritative account ledger for the paper venue.
"""

from __future__ import annotations

from contextlib import suppress
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid5

from core.domain.enums import ExecutionState
from core.schemas import ExecutionReport, Instrument, MarketSnapshot, OrderIntent
from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.config import LoggingConfig
from nautilus_trader.core.datetime import dt_to_unix_nanos
from nautilus_trader.model.data import Bar, BarSpecification, BarType, QuoteTick
from nautilus_trader.model.enums import AccountType, BarAggregation, OmsType, PriceType
from nautilus_trader.model.events import (
    OrderAccepted,
    OrderDenied,
    OrderFilled,
    OrderRejected,
    OrderSubmitted,
)
from nautilus_trader.model.identifiers import TraderId, Venue
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Currency, Money, Price, Quantity
from nautilus_trader.trading.config import StrategyConfig
from nautilus_trader.trading.strategy import Strategy
from pydantic import BaseModel, Field

from adapters.nautilus.mapping import (
    REPORT_NS,
    instrument_to_nautilus,
    order_intent_to_order,
    provenance,
    report_from_order_accepted,
    report_from_order_denied,
    report_from_order_filled,
    report_from_order_rejected,
    report_from_order_submitted,
)
from adapters.nautilus.models import ConfigurableSlippageFillModel, NotionalCommissionFeeModel

__all__ = ["NautilusPaperExecutor", "PaperVenueConfig"]

_QUOTE_SIZE = 1_000_000
_WINDOW_SECONDS = 2


class PaperVenueConfig(BaseModel):
    """Venue parameters for the Nautilus paper simulator.

    ``slippage_*`` and ``commission_*`` feed the same deterministic models as
    ``adapters.nautilus.models`` (BACKTEST); ``seed`` keeps fills reproducible.
    """

    trader_id: str = Field(default="PAPER-001", min_length=1)
    venue_name: str = Field(default="PAPER", min_length=1)
    account_currency: str = Field(default="USD", min_length=3, max_length=4)
    # Venue-internal working capital (never the pipeline's authoritative
    # paper account — that lives in PaperAccountRecord). Large enough that
    # venue-side balance checks never reject normal paper sizes.
    starting_balance: Decimal = Field(default=Decimal("1000000"), gt=0)
    seed: int = 7
    slippage_fixed_ticks: int = Field(default=0, ge=0)
    slippage_random_min_ticks: int = Field(default=0, ge=0)
    slippage_random_max_ticks: int = Field(default=0, ge=0)
    commission_rate_bps: Decimal = Field(default=Decimal("0.5"), ge=0)
    commission_min_amount: Decimal = Field(default=Decimal("0"), ge=0)
    prob_fill_on_limit: float = Field(default=1.0, ge=0, le=1)
    prob_fill_on_stop: float = Field(default=1.0, ge=0, le=1)


class _PaperSubmitStrategy(Strategy):  # type: ignore[misc]
    """Submits exactly one order on the first quote tick of the mini-run."""

    def __init__(
        self,
        *,
        intent: OrderIntent,
        trader_id: str,
        nautilus_instrument: CurrencyPair,
        bar_type: BarType,
        executor: NautilusPaperExecutor,
    ) -> None:
        super().__init__(StrategyConfig(strategy_id="PAPER-SUBMIT-001", order_id_tag="001"))
        self._intent = intent
        self._trader_id = trader_id
        self._instrument = nautilus_instrument
        self._bar_type = bar_type
        self._executor = executor
        self._submitted = False

    def on_start(self) -> None:
        self.subscribe_bars(self._bar_type)
        self.subscribe_quote_ticks(self._bar_type.instrument_id)

    def on_quote_tick(self, tick: QuoteTick) -> None:
        if self._submitted:
            return
        self._submitted = True
        ts_init_ns = dt_to_unix_nanos(tick.ts_init)
        order = order_intent_to_order(
            self._intent,
            TraderId(self._trader_id),
            self.id,
            self._instrument,
            ts_init_ns,
        )
        self.submit_order(order)

    # ── order event capture → ExecutionReport ─────────────────────────────────

    def on_order_submitted(self, event: OrderSubmitted) -> None:
        self._executor.on_report(
            report_from_order_submitted(
                event, self._intent, self._executor.next_sequence(), self._executor.venue_name
            )
        )

    def on_order_accepted(self, event: OrderAccepted) -> None:
        self._executor.on_report(
            report_from_order_accepted(
                event, self._intent, self._executor.next_sequence(), self._executor.venue_name
            )
        )

    def on_order_rejected(self, event: OrderRejected) -> None:
        self._executor.on_report(
            report_from_order_rejected(
                event, self._intent, self._executor.next_sequence(), self._executor.venue_name
            )
        )

    def on_order_denied(self, event: OrderDenied) -> None:
        self._executor.on_report(
            report_from_order_denied(
                event, self._intent, self._executor.next_sequence(), self._executor.venue_name
            )
        )

    def on_order_filled(self, event: OrderFilled) -> None:
        self._executor.filled_total += event.last_qty.as_decimal()
        self._executor.on_report(
            report_from_order_filled(
                event,
                self._intent,
                self._executor.next_sequence(),
                self._executor.venue_name,
                self._executor.filled_total,
            )
        )


class NautilusPaperExecutor:
    """One-shot Nautilus paper venue: OrderIntent + snapshot → ExecutionReports.

    Deterministic given the config seed: the same intent and snapshot always
    produce the same report sequence. Never sends anything to a real broker —
    the venue exists only inside the mini ``BacktestEngine``.
    """

    def __init__(self, config: PaperVenueConfig, instrument: Instrument) -> None:
        self._config = config
        self._instrument = instrument
        self._venue = Venue(config.venue_name)
        self._nautilus_instrument = instrument_to_nautilus(instrument, self._venue)
        self._reports: list[ExecutionReport] = []
        self._sequence = 0
        self.filled_total: Decimal = Decimal("0")

    @property
    def venue_name(self) -> str:
        return self._config.venue_name

    def next_sequence(self) -> int:
        self._sequence += 1
        return self._sequence

    def on_report(self, report: ExecutionReport) -> None:
        self._reports.append(report)

    def submit(self, intent: OrderIntent, snapshot: MarketSnapshot) -> list[ExecutionReport]:
        """Execute one OrderIntent against the snapshot's bid/ask.

        Returns the canonical report sequence; a mapping/venue failure degrades
        to a REJECTED report — the caller must never treat a failed submission
        as a fill (INV-6).
        """
        self._reports = []
        self._sequence = 0
        self.filled_total = Decimal("0")
        as_of = snapshot.as_of
        try:
            self._run_engine(intent, snapshot, as_of)
        except Exception as exc:  # venue-side failure: reject, never fill
            self._reports.append(
                ExecutionReport(
                    execution_report_id=uuid5(
                        REPORT_NS,
                        f"{intent.order_intent_id}:reject:{type(exc).__name__}",
                    ),
                    order_intent_id=intent.order_intent_id,
                    venue=self._config.venue_name,
                    status=ExecutionState.REJECTED,
                    reject_reason=f"{type(exc).__name__}: {exc}"[:500],
                    report_time=as_of,
                    sequence=1,
                    produced_at=as_of,
                    provenance=provenance(as_of),
                )
            )
        self._synthesize_ack()
        return self._reports

    def _synthesize_ack(self) -> None:
        """Instant market-order fills in Nautilus backtests can skip the
        OrderAccepted event. The canonical chain requires an ACKNOWLEDGED
        report between SUBMITTED and FILLED (INV-6), so one is synthesized
        from the fill — mirroring the applier's fill-before-ACK healing."""
        has_ack = any(r.status is ExecutionState.ACKNOWLEDGED for r in self._reports)
        fills = [r for r in self._reports if r.status is ExecutionState.FILLED]
        if has_ack or not fills:
            return
        fill = fills[0]
        ack = ExecutionReport(
            execution_report_id=uuid5(REPORT_NS, f"{fill.order_intent_id}:ack-synth"),
            order_intent_id=fill.order_intent_id,
            venue=self._config.venue_name,
            venue_order_id=fill.venue_order_id,
            status=ExecutionState.ACKNOWLEDGED,
            report_time=fill.report_time,
            sequence=fill.sequence,
            produced_at=fill.report_time,
            provenance=provenance(fill.report_time),
        )
        inserted = False
        for index, report in enumerate(self._reports):
            if report.status is ExecutionState.FILLED:
                self._reports.insert(index, ack)
                inserted = True
                break
        if not inserted:
            self._reports.append(ack)

    def _run_engine(self, intent: OrderIntent, snapshot: MarketSnapshot, as_of: datetime) -> None:
        config = self._config
        engine = BacktestEngine(
            BacktestEngineConfig(
                trader_id=TraderId(config.trader_id),
                logging=LoggingConfig(log_level="ERROR"),
            )
        )
        fill_model = ConfigurableSlippageFillModel(
            fixed_ticks=config.slippage_fixed_ticks,
            random_min_ticks=config.slippage_random_min_ticks,
            random_max_ticks=config.slippage_random_max_ticks,
            seed=config.seed,
            prob_fill_on_limit=config.prob_fill_on_limit,
            prob_fill_on_stop=config.prob_fill_on_stop,
        )
        fee_model = NotionalCommissionFeeModel(
            rate_bps=config.commission_rate_bps,
            min_amount=config.commission_min_amount,
        )
        base_currency = self._instrument.base_currency
        if base_currency is None:
            raise ValueError("FX instrument requires base_currency")
        bar_type = BarType(
            instrument_id=self._nautilus_instrument.id,
            bar_spec=BarSpecification(1, BarAggregation.MINUTE, PriceType.MID),
        )
        try:
            engine.add_venue(
                venue=self._venue,
                oms_type=OmsType.NETTING,
                account_type=AccountType.CASH,
                starting_balances=[
                    Money(config.starting_balance, Currency.from_str(config.account_currency)),
                    Money(config.starting_balance, Currency.from_str(base_currency)),
                ],
                base_currency=None,
                fill_model=fill_model,
                fee_model=fee_model,
                use_random_ids=False,
                reject_stop_orders=False,
                bar_execution=False,  # fills from the snapshot quotes, never bars
            )
            engine.add_instrument(self._nautilus_instrument)
            engine.add_data(self._quotes(snapshot))
            engine.add_data(self._bars(snapshot, bar_type))
            strategy = _PaperSubmitStrategy(
                intent=intent,
                trader_id=config.trader_id,
                nautilus_instrument=self._nautilus_instrument,
                bar_type=bar_type,
                executor=self,
            )
            engine.add_strategy(strategy)
            engine.run(start=as_of, end=as_of + timedelta(seconds=_WINDOW_SECONDS))
        finally:
            with suppress(Exception):  # dispose is best-effort
                engine.dispose()

    # ── market data from one snapshot ─────────────────────────────────────────

    def _quotes(self, snapshot: MarketSnapshot) -> list[QuoteTick]:
        ts_ns = dt_to_unix_nanos(snapshot.as_of)
        return [
            QuoteTick(
                instrument_id=self._nautilus_instrument.id,
                bid_price=Price.from_str(str(snapshot.bid)),
                ask_price=Price.from_str(str(snapshot.ask)),
                bid_size=Quantity(_QUOTE_SIZE, 0),
                ask_size=Quantity(_QUOTE_SIZE, 0),
                ts_event=ts_ns,
                ts_init=ts_ns,
            )
        ]

    def _bars(self, snapshot: MarketSnapshot, bar_type: BarType) -> list[Bar]:
        ts_ns = dt_to_unix_nanos(snapshot.as_of)
        mid = snapshot.mid
        open_ = snapshot.open or mid
        high = snapshot.high or mid
        low = snapshot.low or mid
        close = snapshot.close or mid
        volume = int(snapshot.volume) if snapshot.volume is not None else 0
        return [
            Bar(
                bar_type=bar_type,
                open=Price.from_str(str(open_)),
                high=Price.from_str(str(high)),
                low=Price.from_str(str(low)),
                close=Price.from_str(str(close)),
                volume=Quantity(volume, 0),
                ts_event=ts_ns,
                ts_init=ts_ns,
            )
        ]
