"""One deterministic trading cycle: quotes → signal → proposal → Risk Engine → submit.

The engine never touches a socket itself: quotes arrive from the MT4 client,
the Risk Engine decides, and the ``OrderSubmitter`` (the execution service in
production, a fake in tests) is the only way an order can leave the engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from adapters.mt4.protocol import MarketQuote
from core.domain.enums import (
    OperatingMode,
    OrderSide,
    OrderType,
    RiskDecisionType,
    SignalDirection,
    TimeInForce,
)
from core.schemas import (
    Instrument,
    MarketSnapshot,
    OrderIntent,
    Provenance,
    RiskDecision,
    TradeProposal,
)
from core.schemas.risk import AccountState, PortfolioState, RiskPolicy, StrategyConfiguration
from engines.execution.live_gate import PriceContext
from engines.risk.engine import evaluate_proposal

from apps.live_supervisor.config import (
    LiveSupervisorConfig,
    build_instrument,
    build_live_policy,
    build_strategy_configuration,
)
from apps.live_supervisor.signals import MinuteBarSeries, floor_to_step, scalp_signal

__all__ = ["CycleOutcome", "LiveTradingEngine", "OrderSubmitter"]

_PROPOSAL_NS = UUID("6b0e4c4e-1c4e-5d3e-9a1f-0a2b3c4d5e6f")


class OrderSubmitter(Protocol):
    def submit(
        self,
        intent: OrderIntent,
        *,
        price_context: PriceContext,
        risk_decision: RiskDecision,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class CycleOutcome:
    instrument_id: str
    decision: str
    detail: str
    order_intent_id: UUID | None = None


class LiveTradingEngine:
    """Deterministic LIVE_AUTO cycle engine (INV-1: no LLM anywhere)."""

    def __init__(
        self,
        config: LiveSupervisorConfig,
        clock,
        submitter: OrderSubmitter,
        *,
        policy: RiskPolicy | None = None,
        instruments: dict[str, Instrument] | None = None,
        strategy: StrategyConfiguration | None = None,
    ) -> None:
        self._config = config
        self._clock = clock
        self._submitter = submitter
        self._policy = policy or build_live_policy(config, clock.now())
        self._instruments = instruments or {
            iid: build_instrument(iid, clock.now()) for iid in config.instruments
        }
        self._strategy = strategy or build_strategy_configuration(config, clock.now())
        self._series = {iid: MinuteBarSeries() for iid in config.instruments}

    # ── Quote ingestion ────────────────────────────────────────────────────
    def on_quote(self, quote: MarketQuote) -> None:
        series = self._series.get(quote.symbol)
        if series is None:
            return
        series.on_price((quote.bid + quote.ask) / 2, quote.timestamp)

    def closed_bars(self, instrument_id: str):
        """Closed minute bars for the Strategy Lab persistence path."""
        series = self._series.get(instrument_id)
        if series is None:
            return ()
        return series.bars()

    def seed_bars(self, instrument_id: str, bars) -> None:
        """Pre-warm the series with persisted bars (restart without cold start)."""
        series = self._series.get(instrument_id)
        if series is None or series.bars():
            return
        for bar in bars:
            series.on_price(bar.open, bar.closed_at)
            series.on_price(bar.high, bar.closed_at)
            series.on_price(bar.low, bar.closed_at)
            series.on_price(bar.close, bar.closed_at)

    # ── Cycle ──────────────────────────────────────────────────────────────
    def cycle(
        self,
        *,
        account: AccountState,
        portfolio: PortfolioState,
        quotes: dict[str, MarketQuote],
        now: datetime | None = None,
    ) -> list[CycleOutcome]:
        now = now or self._clock.now()
        outcomes: list[CycleOutcome] = []
        open_instruments = {p.instrument_id for p in portfolio.positions}
        for instrument_id in self._config.instruments:
            outcome = self._cycle_one(
                instrument_id, account, portfolio, open_instruments, quotes, now
            )
            if outcome is not None:
                outcomes.append(outcome)
        return outcomes

    def _cycle_one(
        self,
        instrument_id: str,
        account: AccountState,
        portfolio: PortfolioState,
        open_instruments: set[str],
        quotes: dict[str, MarketQuote],
        now: datetime,
    ) -> CycleOutcome | None:
        quote = quotes.get(instrument_id)
        if quote is None:
            return None
        if instrument_id in open_instruments:
            return CycleOutcome(
                instrument_id, "SKIP", f"open position on {instrument_id}"
            )
        if len(open_instruments) >= self._policy.max_positions:
            return CycleOutcome(instrument_id, "SKIP", "max open positions reached")

        age = now - quote.timestamp
        if age > timedelta(seconds=self._policy.market_data_max_age_seconds):
            return CycleOutcome(
                instrument_id, "SKIP", f"quote stale ({age.total_seconds():.1f}s)"
            )
        if not quote.tradable:
            return CycleOutcome(instrument_id, "SKIP", "symbol not tradable")

        instrument = self._instruments[instrument_id]
        spread_points = quote.spread / instrument.tick_size
        if spread_points > self._config.max_spread_points:
            return CycleOutcome(
                instrument_id, "SKIP", f"spread {spread_points:.1f} points above ceiling"
            )

        series = self._series[instrument_id]
        if len(series.bars()) < self._config.warmup_bars:
            return CycleOutcome(instrument_id, "SKIP", "warming up bars")

        signal = scalp_signal(series, self._config.signal_params)
        if not signal.tradable or signal.atr <= 0:
            return CycleOutcome(instrument_id, "FLAT", f"strength {signal.strength:.6f}")

        proposal = self._build_proposal(
            instrument_id, instrument, signal, quote, now, account.equity
        )
        snapshot = MarketSnapshot(
            instrument_id=instrument_id,
            as_of=now,
            source_timestamp=quote.timestamp,
            bid=quote.bid,
            ask=quote.ask,
            last=(quote.bid + quote.ask) / 2,
            high=max(quote.bid, quote.ask),
            low=min(quote.bid, quote.ask),
            close=(quote.bid + quote.ask) / 2,
            volume=None,
            timeframe=None,
            source="mt4-quotes",
            produced_at=now,
            provenance=Provenance(producer="apps.live_supervisor", produced_at=now),
        )
        decision = evaluate_proposal(
            proposal=proposal,
            account=account,
            portfolio=portfolio,
            snapshot=snapshot,
            strategy=self._strategy,
            policy=self._policy,
            instrument=instrument,
        )
        if decision.decision is RiskDecisionType.REJECT:
            return CycleOutcome(
                instrument_id,
                "RISK_REJECTED",
                ", ".join(code.value for code in decision.reason_codes),
            )
        if decision.approved_quantity is None or decision.approved_stop is None:
            return CycleOutcome(instrument_id, "REJECTED", "decision missing approved values")

        intent = OrderIntent(
            order_intent_id=uuid5(_PROPOSAL_NS, f"{proposal.proposal_id}:{now.timestamp():.3f}"),
            risk_decision_id=decision.decision_id,
            proposal_id=proposal.proposal_id,
            strategy_id=self._config.strategy_id,
            strategy_version=self._config.strategy_version,
            instrument_id=instrument_id,
            operating_mode=OperatingMode.LIVE_AUTO,
            side=OrderSide.BUY if proposal.direction is SignalDirection.LONG else OrderSide.SELL,
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.GTC,
            quantity=decision.approved_quantity,
            stop_loss=decision.approved_stop,
            take_profit=proposal.take_profit,
            max_slippage=(instrument.tick_size * Decimal("5")),
            valid_until=now + timedelta(seconds=60),
            created_by="live-supervisor",
            produced_at=now,
            provenance=Provenance(producer="apps.live_supervisor", produced_at=now),
        )
        price_context = PriceContext(bid=quote.bid, ask=quote.ask, observed_at=quote.timestamp)
        self._submitter.submit(intent, price_context=price_context, risk_decision=decision)
        return CycleOutcome(
            instrument_id,
            decision.decision.value,
            f"qty={intent.quantity} stop={intent.stop_loss} tp={intent.take_profit}",
            order_intent_id=intent.order_intent_id,
        )

    # ── Proposal builder (deterministic; Risk Engine re-sizes, INV-1) ──────
    def _build_proposal(
        self,
        instrument_id: str,
        instrument: Instrument,
        signal,
        quote: MarketQuote,
        now: datetime,
        equity: Decimal,
    ) -> TradeProposal:
        mid = (quote.bid + quote.ask) / 2
        notional_per_lot = instrument.contract_size * mid
        raw_lots = equity * self._config.position_equity_pct / notional_per_lot
        lots = max(
            instrument.min_lot,
            min(instrument.max_lot, floor_to_step(raw_lots, instrument.lot_step)),
        )
        tick = instrument.tick_size
        stop_distance = max(
            (signal.atr * self._config.stop_atr_ratio),
            self._policy.min_stop_distance,
        )
        stop_distance = (stop_distance / tick).to_integral_value() * tick
        take_distance = (signal.atr * self._config.take_atr_ratio / tick).to_integral_value() * tick
        if signal.direction is SignalDirection.LONG:
            stop = mid - stop_distance
            take = mid + take_distance
            direction = SignalDirection.LONG
        else:
            stop = mid + stop_distance
            take = mid - take_distance
            direction = SignalDirection.SHORT
        if stop <= 0 or take <= 0:
            raise ValueError("proposal stop/take must be positive")
        return TradeProposal(
            proposal_id=uuid5(_PROPOSAL_NS, f"{instrument_id}:{now.timestamp():.3f}:{mid}"),
            strategy_id=self._config.strategy_id,
            strategy_version=self._config.strategy_version,
            instrument_id=instrument_id,
            operating_mode=OperatingMode.LIVE_AUTO,
            direction=direction,
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.GTC,
            quantity=lots,
            stop_loss=stop,
            take_profit=take,
            source_signal_ids=[f"ema{12}-ema{45}:{instrument_id}"],
            rationale=(
                f"deterministic EMA cross {direction.value} "
                f"strength={signal.strength:.6f} atr={signal.atr}"
            ),
            expires_at=now + timedelta(seconds=60),
            produced_at=now,
            provenance=Provenance(producer="apps.live_supervisor", produced_at=now),
        )
