"""Shared builders for the autonomous paper pipeline test suite.

Builds a complete in-memory pipeline stack (stores, bus, ledger, adapters,
Nautilus paper venue) driven by a :class:`core.clock.VirtualClock` so tests are
deterministic. Imported as ``from worker_helpers import ...`` (tests/ is on the
pytest pythonpath).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from adapters.graphiti.memory import Memory
from adapters.graphiti.store import InMemoryStore
from adapters.nautilus.paper import NautilusPaperExecutor
from adapters.obsidian import MemoryVaultWriter
from adapters.tradingagents.mock import MockTradingAgentsAdapter
from apps.worker.bus import InMemoryStreamBus
from apps.worker.cli import build_default_config
from apps.worker.config import make_instrument, make_paper_venue
from apps.worker.ledger import PaperLedger
from apps.worker.persistence import InMemoryPipelineStore
from apps.worker.pipeline import PaperPipeline, build_paper_runtime
from apps.worker.scheduler import UnattendedPaperRunner
from apps.worker.sources import SnapshotSource
from apps.worker.stages import (
    accounting,
    execution,
    fusion,
    order_intent,
    positions,
    posttrade,
    proposal,
    research,
    risk,
)
from core.audit.audit import AuditLogger, InMemoryAuditSink
from core.clock.clocks import Clock
from core.config.settings import Settings
from core.schemas import MarketSnapshot
from engines.execution.persistence import InMemoryExecutionStateStore
from engines.posttrade.artifacts import MemoryArtifactStore
from engines.posttrade.persistence import InMemoryPostTradeStore

from factories import FIXED_START, make_market_snapshot

__all__ = ["PaperStack", "build_paper_stack", "make_audit", "scripted_snapshots"]


def make_audit(clock: Clock) -> tuple[AuditLogger, InMemoryAuditSink]:
    sink = InMemoryAuditSink()
    return AuditLogger(sink, clock), sink


class PaperStack:
    """A fully wired in-memory paper pipeline."""

    def __init__(
        self,
        *,
        config: Any,
        clock: Clock,
        store: InMemoryPipelineStore,
        bus: InMemoryStreamBus,
        execution_store: InMemoryExecutionStateStore,
        ledger: PaperLedger,
        rt: Any,
        pipeline: PaperPipeline,
        runner: UnattendedPaperRunner,
        source: SnapshotSource,
        audit_sink: InMemoryAuditSink,
        posttrade_store: Any,
        artifact_store: Any,
        vault_writer: Any,
    ) -> None:
        self.config = config
        self.clock = clock
        self.store = store
        self.bus = bus
        self.execution_store = execution_store
        self.ledger = ledger
        self.rt = rt
        self.pipeline = pipeline
        self.runner = runner
        self.source = source
        self.audit_sink = audit_sink
        self.posttrade_store = posttrade_store
        self.artifact_store = artifact_store
        self.vault_writer = vault_writer


def build_paper_stack(
    *,
    clock: Clock,
    settings: Settings,
    tradingagents: object | None = None,
    source: SnapshotSource | None = None,
    config_overrides: dict[str, Any] | None = None,
    memory: Memory | None = None,
    artifact_store: Any | None = None,
    vault_writer: Any | None = None,
) -> PaperStack:
    """Assemble the full stack; LLM, snapshot source and side-effect sinks
    (memory, artifacts, vault) are injectable for fault-injection tests."""

    config = build_default_config(settings)
    if config_overrides:
        config = config.model_copy(update=config_overrides)
    store = InMemoryPipelineStore()
    bus = InMemoryStreamBus(clock=clock)
    execution_store = InMemoryExecutionStateStore()
    instruments = {
        iid: make_instrument(config.instruments[iid], clock.now()) for iid in config.watchlist
    }
    ledger = PaperLedger(
        account_id=config.account_id,
        currency=config.account_currency,
        lot_size=Decimal("100000"),
        instrument_by_id=instruments,
        execution_store=execution_store,
        clock=clock,
    )
    snapshot_source = source or scripted_snapshots()
    executors = {
        iid: NautilusPaperExecutor(make_paper_venue(config), instruments[iid])
        for iid in config.watchlist
    }
    memory = memory or Memory(InMemoryStore(), clock=clock)
    adapter = (
        tradingagents
        if tradingagents is not None
        else MockTradingAgentsAdapter(clock_now=clock.now)
    )
    audit, audit_sink = make_audit(clock)
    posttrade_store = InMemoryPostTradeStore()
    artifact_store = artifact_store or MemoryArtifactStore()
    vault_writer = vault_writer or MemoryVaultWriter()
    rt = build_paper_runtime(
        config=config,
        store=store,
        bus=bus,
        execution_store=execution_store,
        ledger=ledger,
        snapshot_source=snapshot_source,
        tradingagents=adapter,
        memory=memory,
        paper_executor=executors,
        posttrade_store=posttrade_store,
        artifact_store=artifact_store,
        vault_writer=vault_writer,
        clock=clock,
        audit=audit,
    )
    pipeline = PaperPipeline(
        [
            research.ResearchStage(),
            fusion.FusionStage(),
            proposal.ProposalStage(),
            risk.RiskStage(),
            order_intent.OrderIntentStage(),
            execution.PaperExecutionStage(),
            positions.PositionsStage(),
            accounting.AccountingStage(),
            posttrade.PosttradeStage(),
        ]
    )
    runner = UnattendedPaperRunner(rt=rt, pipeline=pipeline, bus=bus, config=config, clock=clock)
    return PaperStack(
        config=config,
        clock=clock,
        store=store,
        bus=bus,
        execution_store=execution_store,
        ledger=ledger,
        rt=rt,
        pipeline=pipeline,
        runner=runner,
        source=snapshot_source,
        audit_sink=audit_sink,
        posttrade_store=posttrade_store,
        artifact_store=artifact_store,
        vault_writer=vault_writer,
    )


class scripted_snapshots(SnapshotSource):
    """Deterministic scripted snapshots: a fixed mid per (instrument, step)."""

    def __init__(self, script: dict[str, list[Decimal]] | None = None) -> None:
        self._script = script or {
            "EURUSD": [Decimal("1.10000"), Decimal("1.10050"), Decimal("1.10100")]
        }
        self._calls = 0

    @property
    def calls(self) -> int:
        return self._calls

    def latest(self, instrument_id: str, *, now: datetime, step: int) -> MarketSnapshot:
        self._calls += 1
        mids = self._script.get(instrument_id, [Decimal("1.10000")])
        index = max(step - 1, 0)
        mid = mids[min(index, len(mids) - 1)]
        tick = Decimal("0.00001")
        return make_market_snapshot(
            now,
            instrument_id=instrument_id,
            bid=mid - tick,
            ask=mid + tick,
            open=mid - tick,
            high=mid + Decimal("0.0005"),
            low=mid - Decimal("0.0005"),
            close=mid,
            source="worker-tests:scripted",
        )


def fixed_start() -> datetime:
    return FIXED_START
