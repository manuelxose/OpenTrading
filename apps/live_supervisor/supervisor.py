"""Long-running LIVE_AUTO supervisor: startup gate, deterministic cycles, safety loop.

Startup is fail-closed (INV-6): the supervisor refuses to originate any order
until a clean reconciliation proves the broker is reachable, the account is a
DEMO account and no material divergence exists. Afterwards every cycle runs:

  drain events → emergency check → collect quotes → reconcile (account +
  positions) → deterministic engine cycle (Risk Engine + LIVE_AUTO registry)
  → sleep.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from adapters.mt4.client import Mt4ExecutionClient
from adapters.mt4.protocol import MarketQuote, ReconciliationResponse
from core.clock.clocks import Clock, SystemClock
from core.config.settings import Settings, get_settings
from core.domain.enums import AssetClass, OperatingMode, PositionSide
from core.schemas import PositionSnapshot, Provenance
from core.schemas.risk import AccountState, PortfolioExposure, PortfolioState
from engines.execution.live_runtime import build_live_execution_runtime
from engines.execution.service import ExecutionService

from apps.live_supervisor.config import (
    LiveSupervisorConfig,
    build_instrument,
    build_live_policy,
    build_strategy_configuration,
)
from apps.live_supervisor.engine import CycleOutcome, LiveTradingEngine
logger = logging.getLogger("live-supervisor")

__all__ = ["ServiceSubmitter", "run_once", "serve"]


class ServiceSubmitter:
    """Adapts the ExecutionService to the engine's submitter protocol."""

    def __init__(self, service: ExecutionService) -> None:
        self._service = service

    def submit(self, intent, *, price_context, risk_decision) -> object:
        return self._service.submit(
            intent, venue="mt4", price_context=price_context, risk_decision=risk_decision
        )


def collect_latest_quotes(
    client: Mt4ExecutionClient,
    instruments: tuple[str, ...],
    *,
    max_wait_ms: int = 3000,
    idle_stop_ms: int = 250,
) -> dict[str, MarketQuote]:
    """Drain the SUB queue to real time and return the freshest quote per symbol.

    The EA publishes ~18 messages/second; a 60s supervision sleep queues
    thousands of frames. Only polling for a fixed 2s window would hand the
    engine stale quotes from the backlog — instead the socket is drained until
    it goes quiet (idle_stop_ms), bounded by max_wait_ms.
    """
    wanted = set(instruments)
    latest: dict[str, MarketQuote] = {}
    deadline = time.monotonic() + max_wait_ms / 1000.0
    idle_ms = 0
    while time.monotonic() < deadline:
        item = client.poll_quote(timeout_ms=25)
        if item is None:
            idle_ms += 25
            if idle_ms >= idle_stop_ms:
                break
            continue
        idle_ms = 0
        symbol, quote = item
        if symbol in wanted:
            latest[symbol] = quote
    return latest


def broker_positions_to_portfolio(
    response: ReconciliationResponse,
    instruments: tuple[str, ...],
    now: datetime,
) -> PortfolioState:
    contract_by_instrument = {iid: build_instrument(iid, now).contract_size for iid in instruments}
    positions: list[PositionSnapshot] = []
    exposure = PortfolioExposure()
    for venue_position in response.positions:
        canonical = venue_position.position
        if canonical.instrument_id not in contract_by_instrument:
            continue
        mark = canonical.mark_price or Decimal("0")
        notional = canonical.quantity * contract_by_instrument[canonical.instrument_id] * mark
        positions.append(
            PositionSnapshot(
                position_id=canonical.position_id,
                account_id=canonical.account_id,
                strategy_id=canonical.strategy_id or None,
                instrument_id=canonical.instrument_id,
                side=PositionSide.LONG
                if canonical.side is PositionSide.LONG
                else PositionSide.SHORT,
                quantity=canonical.quantity,
                average_entry_price=canonical.average_entry_price,
                mark_price=canonical.mark_price,
                as_of=canonical.as_of,
                produced_at=now,
                provenance=Provenance(producer="apps.live_supervisor", produced_at=now),
            )
        )
        exposure.total_notional += notional
        exposure.by_instrument[canonical.instrument_id] = (
            exposure.by_instrument.get(canonical.instrument_id, Decimal("0")) + notional
        )
        exposure.by_asset_class[AssetClass.CRYPTO] = (
            exposure.by_asset_class.get(AssetClass.CRYPTO, Decimal("0")) + notional
        )
        signed = notional if canonical.side is PositionSide.LONG else -notional
        exposure.net_by_currency["USD"] = exposure.net_by_currency.get("USD", Decimal("0")) + signed
    return PortfolioState(
        account_id=response.account.account_id,
        positions=positions,
        pending_order_count=len(response.open_order_intent_ids),
        exposure=exposure,
        as_of=now,
        produced_at=now,
        provenance=Provenance(producer="apps.live_supervisor", produced_at=now),
    )


def core_account_state(response: ReconciliationResponse, now: datetime) -> AccountState:
    proto = response.account
    return AccountState(
        account_id=proto.account_id,
        currency=proto.currency,
        balance=proto.balance,
        equity=proto.equity,
        free_margin=proto.free_margin,
        leverage=Decimal("100"),
        peak_equity=proto.equity,
        daily_pnl=Decimal("0"),
        consecutive_losses=0,
        last_loss_at=None,
        broker_connected=response.broker_connected,
        last_heartbeat_at=now if response.broker_connected else None,
        safe_mode=False,
        as_of=proto.as_of,
        produced_at=now,
        provenance=Provenance(producer="apps.live_supervisor", produced_at=now),
    )


def _build_engine(config: LiveSupervisorConfig, clock: Clock, submitter) -> LiveTradingEngine:
    now = clock.now()
    return LiveTradingEngine(
        config,
        clock,
        submitter,
        policy=build_live_policy(config, now),
        instruments={iid: build_instrument(iid, now) for iid in config.instruments},
        strategy=build_strategy_configuration(config, now),
    )


def run_once(settings: Settings | None = None, *, timeout_seconds: int = 120) -> int:
    """Startup-gated single cycle (used by ops automation and tests)."""
    settings = settings or get_settings()
    if settings.operating_mode is not OperatingMode.LIVE_AUTO:
        raise RuntimeError("live supervisor requires OT_OPERATING_MODE=LIVE_AUTO")
    config = LiveSupervisorConfig.from_settings(settings)
    clock = SystemClock()
    runtime = build_live_execution_runtime(settings, clock=clock)
    runtime.connect_and_reconcile()
    try:
        # INV-6 startup gate: a clean reconciliation is mandatory.
        gate_ok = False
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            outcome = runtime.service.startup_reconciliation()
            print(
                f"startup reconciliation: broker_reachable={outcome.broker_reachable} "
                f"safe_mode={outcome.safe_mode_active} "
                f"material={outcome.material_discrepancies}"
            )
            if outcome.broker_reachable and not outcome.safe_mode_active:
                gate_ok = True
                break
            time.sleep(10)
        if not gate_ok:
            print("startup gate failed: broker unreachable or SAFE_MODE active — no orders.")
            return 2

        engine = _build_engine(config, clock, ServiceSubmitter(runtime.service))
        response = runtime.client.reconcile()
        runtime.client.resync_sequences(response.last_sequences)
        account = core_account_state(response, clock.now())
        quotes: dict[str, MarketQuote] = {}
        # Warm the quote series first, then run one cycle.
        collected = collect_latest_quotes(runtime.client, config.instruments)
        for quote in collected.values():
            engine.on_quote(quote)
        outcomes = engine.cycle(
            account=account,
            portfolio=broker_positions_to_portfolio(response, config.instruments, clock.now()),
            quotes=collected,
        )
        for outcome in outcomes:
            print(
                f"[{outcome.instrument_id}] {outcome.decision}: {outcome.detail} "
                + (f"intent={outcome.order_intent_id}" if outcome.order_intent_id else "")
            )
        return 0
    finally:
        runtime.client.close()


def serve(settings: Settings | None = None) -> None:
    """Continuous supervision loop (Ctrl+C to stop)."""
    settings = settings or get_settings()
    if settings.operating_mode is not OperatingMode.LIVE_AUTO:
        raise RuntimeError("live supervisor requires OT_OPERATING_MODE=LIVE_AUTO")
    config = LiveSupervisorConfig.from_settings(settings)
    clock = SystemClock()
    runtime = build_live_execution_runtime(settings, clock=clock)
    runtime.connect_and_reconcile()
    logger.info("live supervisor starting: strategy=%s instruments=%s", config.strategy_id, config.instruments)
    try:
        # Startup gate (INV-6): refuse to trade until clean.
        gate_ok = False
        while True:
            outcome = runtime.service.startup_reconciliation()
            logger.info(
                "startup reconciliation: reachable=%s safe_mode=%s material=%d",
                outcome.broker_reachable,
                outcome.safe_mode_active,
                outcome.material_discrepancies,
            )
            if outcome.broker_reachable and not outcome.safe_mode_active:
                gate_ok = True
                break
            time.sleep(10)

        engine = _build_engine(config, clock, ServiceSubmitter(runtime.service))
        logger.info(
            "startup gate passed — automated cycles begin (interval %ds)",
            config.cycle_interval_seconds,
        )

        bars_store = None
        last_persisted: dict[str, datetime | None] = {iid: None for iid in config.instruments}
        if config.persist_bars:
            import sqlalchemy as sa

            from core.config.settings import ensure_psycopg_dsn

            from apps.live_supervisor.bars_store import BarsStore

            bars_store = BarsStore(sa.create_engine(ensure_psycopg_dsn(settings.postgres_dsn)))
            for instrument_id in config.instruments:
                history = bars_store.load_bars(instrument_id, limit=400)
                if history:
                    engine.seed_bars(instrument_id, history)
                    last_persisted[instrument_id] = history[-1].closed_at
                    logger.info(
                        "seeded %d bars for %s (no cold start)", len(history), instrument_id
                    )

        while True:
            runtime.service.check_emergency()
            runtime.service.drain_events(timeout_ms=0)
            response = runtime.client.reconcile()
            runtime.client.resync_sequences(response.last_sequences)
            if not response.account.is_demo:
                raise RuntimeError("REFUSED: bridge account is not a DEMO account (demo-first policy)")
            account = core_account_state(response, clock.now())
            quotes = collect_latest_quotes(runtime.client, config.instruments)
            for quote in quotes.values():
                engine.on_quote(quote)
            if bars_store is not None:
                for instrument_id in config.instruments:
                    bars = engine.closed_bars(instrument_id)
                    pending = [
                        b
                        for b in bars
                        if last_persisted[instrument_id] is None or b.closed_at > last_persisted[instrument_id]
                    ]
                    if pending:
                        bars_store.upsert_bars(instrument_id, tuple(pending))
                        last_persisted[instrument_id] = pending[-1].closed_at
            portfolio = broker_positions_to_portfolio(response, config.instruments, clock.now())
            outcomes = engine.cycle(account=account, portfolio=portfolio, quotes=quotes)
            for outcome in outcomes:
                logger.info(
                    "[%s] %s: %s%s",
                    outcome.instrument_id,
                    outcome.decision,
                    outcome.detail,
                    f" intent={outcome.order_intent_id}" if outcome.order_intent_id else "",
                )
            time.sleep(config.cycle_interval_seconds)
    except KeyboardInterrupt:
        logger.info("live supervisor stopped by operator")
    finally:
        runtime.client.close()
