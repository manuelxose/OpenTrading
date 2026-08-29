"""Debug script: run the paper pipeline once and print decisions (dev-only)."""

from adapters.graphiti.memory import Memory
from adapters.graphiti.store import InMemoryStore
from adapters.nautilus.paper import NautilusPaperExecutor
from adapters.tradingagents.mock import MockTradingAgentsAdapter
from apps.worker.bus import InMemoryStreamBus
from apps.worker.cli import build_default_config
from apps.worker.config import make_instrument, make_paper_venue
from apps.worker.ledger import PaperLedger
from apps.worker.persistence import InMemoryPipelineStore
from apps.worker.pipeline import PaperPipeline, build_paper_runtime
from apps.worker.scheduler import UnattendedPaperRunner
from apps.worker.sources import SyntheticSnapshotSource
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
from core.clock.clocks import SystemClock
from core.config.settings import get_settings
from engines.execution.persistence import InMemoryExecutionStateStore

clock = SystemClock()
settings = get_settings()
config = build_default_config(settings)
store = InMemoryPipelineStore()
bus = InMemoryStreamBus(clock=clock)
exec_store = InMemoryExecutionStateStore()
ledger = PaperLedger(
    account_id=config.account_id,
    currency=config.account_currency,
    lot_size=100000,
    instrument_by_id={
        iid: make_instrument(config.instruments[iid], clock.now()) for iid in config.watchlist
    },
    execution_store=exec_store,
    clock=clock,
)
src = SyntheticSnapshotSource(
    seed=42,
    instruments={iid: s.initial_mid for iid, s in config.instruments.items()},
    clock=clock,
)
memory = Memory(InMemoryStore(), clock=clock)
executors = {
    iid: NautilusPaperExecutor(
        make_paper_venue(config), make_instrument(config.instruments[iid], clock.now())
    )
    for iid in config.watchlist
}
rt = build_paper_runtime(
    config=config,
    store=store,
    bus=bus,
    execution_store=exec_store,
    ledger=ledger,
    snapshot_source=src,
    tradingagents=MockTradingAgentsAdapter(clock_now=clock.now),
    memory=memory,
    paper_executor=executors,
    clock=clock,
    audit=AuditLogger(InMemoryAuditSink(), clock),
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
runner.run_once()
for lc in store.list_lifecycles():
    print(lc.instrument_id, lc.state.value, "error=", lc.error)
for run in store.list_runs():
    print(run.stage.value, run.status.value, run.error or "", run.output_refs)
