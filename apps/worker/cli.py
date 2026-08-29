"""CLI for the autonomous PAPER pipeline (Phase 7).

    uv run python -m apps.worker run            # unattended serve (Redis Streams)
    uv run python -m apps.worker run-once       # one synchronous cycle, in-process
    uv run python -m apps.worker run --llm mock --store memory --bus memory

Paper mode only: no flag can enable real broker execution in this milestone.
"""

from __future__ import annotations

import argparse
import logging
import sys
from decimal import Decimal

from core.clock.clocks import SystemClock
from core.config.settings import Settings, get_settings
from core.schemas import Instrument
from core.security import assert_llm_process_cannot_execute, install_redacting_logging

from apps.worker.config import PaperPipelineConfig

__all__ = ["build_default_config", "main"]


def build_default_config(settings: Settings) -> PaperPipelineConfig:
    """PaperPipelineConfig from runtime settings (OT_* env / .env)."""
    from adapters.nautilus.paper import PaperVenueConfig

    from apps.worker.config import (
        BusParams,
        InstrumentSpec,
        PostTradeParams,
        ProposalParams,
    )

    instrument_ids = [i.strip() for i in settings.paper_instruments.split(",") if i.strip()]
    instruments: dict[str, InstrumentSpec] = {}
    for index, instrument_id in enumerate(instrument_ids):
        quote = instrument_id[3:6] if len(instrument_id) == 6 else "USD"
        base = instrument_id[:3] if len(instrument_id) == 6 else instrument_id
        instruments[instrument_id] = InstrumentSpec(
            instrument_id=instrument_id,
            base_currency=base,
            quote_currency=quote,
            tick_size=Decimal("0.00001"),
            price_precision=5,
            lot_size=Decimal("100000"),
            lot_step=Decimal("1"),
            min_lot=Decimal("1"),
            max_lot=Decimal("100"),
            initial_mid=Decimal("1.10000") + index * Decimal("0.05"),
        )
    return PaperPipelineConfig(
        starting_balance=settings.paper_starting_balance,
        cycle_interval_seconds=settings.paper_cycle_interval_seconds,
        instruments=instruments,
        llm_enabled=settings.paper_llm_enabled,
        llm_required=settings.paper_llm_required,
        llm_timeout_seconds=settings.paper_llm_timeout_seconds,
        proposal=ProposalParams(
            position_equity_pct=settings.paper_position_equity_pct,
            stop_atr_ratio=settings.paper_stop_atr_ratio,
            take_atr_ratio=settings.paper_take_atr_ratio,
        ),
        venue=PaperVenueConfig(
            slippage_fixed_ticks=settings.paper_slippage_ticks,
            commission_rate_bps=settings.paper_commission_bps,
            seed=7,
        ),
        bus=BusParams(
            stream_key=settings.paper_redis_stream,
            group_prefix=settings.paper_consumer_group_prefix,
            consumer_name=settings.paper_consumer_name,
            max_deliveries=settings.paper_max_deliveries,
            block_ms=settings.paper_block_ms,
            batch_size=settings.paper_batch_size,
            claim_idle_ms=5000,
        ),
        posttrade=PostTradeParams(
            vault_path=settings.posttrade_vault_path,
            artifact_bucket=settings.posttrade_artifact_bucket,
        ),
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="apps.worker", description=__doc__)
    parser.add_argument("command", choices=["run", "run-once"])
    parser.add_argument("--llm", choices=["mock", "live", "off"], default="mock")
    parser.add_argument("--store", choices=["memory", "postgres"], default="memory")
    parser.add_argument("--bus", choices=["memory", "redis"], default="memory")
    parser.add_argument("--artifacts", choices=["memory", "minio"], default="memory")
    parser.add_argument("--data-source", choices=["repository", "synthetic"], default="synthetic")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cycles", type=int, default=1, help="run-once: number of cycles")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    install_redacting_logging()
    settings = get_settings()
    # INV-1 / INV-9 boundary: an LLM-facing process never runs with execution
    # capability. Fail closed before any store, socket or secret is touched.
    assert_llm_process_cannot_execute(settings.operating_mode, process="apps.worker")
    config = build_default_config(settings)
    if args.data_source != "synthetic":
        config = config.model_copy(update={"snapshot_source": args.data_source})
    if args.llm == "off":
        config = config.model_copy(update={"llm_enabled": False})

    from core.audit.audit import AuditLogger, InMemoryAuditSink
    from core.clock.clocks import Clock

    from apps.worker.bus import InMemoryStreamBus, RedisStreamBus
    from apps.worker.persistence import InMemoryPipelineStore, PostgresPipelineStore
    from apps.worker.pipeline import ALL_STAGES, PaperPipeline, build_paper_runtime
    from apps.worker.scheduler import UnattendedPaperRunner

    clock: Clock = SystemClock()

    store = (
        InMemoryPipelineStore()
        if args.store == "memory"
        else PostgresPipelineStore(settings.postgres_dsn)
    )
    bus = (
        InMemoryStreamBus(clock=clock)
        if args.bus == "memory"
        else RedisStreamBus(
            settings.redis_url,
            stream_key=config.bus.stream_key,
            retry_base_seconds=config.bus.retry_base_seconds,
            retry_max_seconds=config.bus.retry_max_seconds,
            max_attempts=None,
        )
    )
    from engines.execution.persistence import (
        InMemoryExecutionStateStore,
        PostgresExecutionStateStore,
    )

    execution_store = (
        InMemoryExecutionStateStore()
        if args.store == "memory"
        else PostgresExecutionStateStore(settings.postgres_dsn)
    )

    from apps.worker.ledger import PaperLedger

    ledger = PaperLedger(
        account_id=config.account_id,
        currency=config.account_currency,
        lot_size=config.instruments[config.watchlist[0]].lot_size,
        instrument_by_id={iid: _instrument(config, iid, clock) for iid in config.watchlist},
        execution_store=execution_store,
        clock=clock,
    )

    from apps.worker.sources import SyntheticSnapshotSource

    if args.data_source == "repository":
        raise SystemExit(
            "--data-source repository requires a wired MarketDataRepository; "
            "use synthetic (default) for the standalone paper demo"
        )
    source = SyntheticSnapshotSource(
        seed=args.seed,
        instruments={iid: spec.initial_mid for iid, spec in config.instruments.items()},
        clock=clock,
    )

    tradingagents = None
    if config.llm_enabled:
        from adapters.tradingagents.mock import MockTradingAgentsAdapter

        tradingagents = MockTradingAgentsAdapter(clock_now=clock.now)

    from adapters.graphiti.memory import Memory
    from adapters.graphiti.store import InMemoryStore

    memory = Memory(InMemoryStore(), clock=clock)

    from adapters.obsidian import (
        FileVaultWriter,
        MirroringEventBus,
        NullVaultWriter,
        ObsidianExporter,
        VaultWriter,
        initialize_vault,
    )
    from engines.posttrade.artifacts import MemoryArtifactStore, MinioArtifactStore
    from engines.posttrade.persistence import InMemoryPostTradeStore, PostgresPostTradeStore

    posttrade_store = (
        InMemoryPostTradeStore()
        if args.store == "memory"
        else PostgresPostTradeStore(settings.postgres_dsn)
    )
    artifact_store = (
        MemoryArtifactStore()
        if args.artifacts == "memory"
        else MinioArtifactStore(
            settings.minio_endpoint,
            settings.minio_access_key,
            settings.minio_secret_key,
            bucket=config.posttrade.artifact_bucket,
            secure=settings.minio_secure,
        )
    )
    vault_writer: VaultWriter
    try:
        initialize_vault(config.posttrade.vault_path)
        vault_writer = FileVaultWriter(config.posttrade.vault_path)
    except OSError as exc:
        logging.getLogger(__name__).warning(
            "Obsidian vault unavailable (%s); continuing without filesystem mirror",
            type(exc).__name__,
        )
        vault_writer = NullVaultWriter()
        config = config.model_copy(
            update={"posttrade": config.posttrade.model_copy(update={"write_vault_notes": False})}
        )
    mirrored_bus = MirroringEventBus(bus, ObsidianExporter(vault_writer))

    paper_executors: dict[str, object] = {}
    from adapters.nautilus.paper import NautilusPaperExecutor

    from apps.worker.config import make_paper_venue

    venue_config = make_paper_venue(config)
    for instrument_id in config.watchlist:
        paper_executors[instrument_id] = NautilusPaperExecutor(
            venue_config, _instrument(config, instrument_id, clock)
        )

    rt = build_paper_runtime(
        config=config,
        store=store,
        bus=mirrored_bus,
        execution_store=execution_store,
        ledger=ledger,
        snapshot_source=source,
        tradingagents=tradingagents,
        memory=memory,
        paper_executor=paper_executors,
        posttrade_store=posttrade_store,
        artifact_store=artifact_store,
        vault_writer=vault_writer,
        clock=clock,
        audit=AuditLogger(InMemoryAuditSink(), clock),
    )
    pipeline = PaperPipeline([stage_cls() for stage_cls in ALL_STAGES])
    runner = UnattendedPaperRunner(
        rt=rt, pipeline=pipeline, bus=mirrored_bus, config=config, clock=clock
    )

    if args.command == "run-once":
        for _ in range(args.cycles):
            events = runner.run_once()
        print(f"run-once complete: {len(events)} events produced")
        runs = store.list_runs()
        print(f"pipeline runs recorded: {len(runs)}")
        lifecycles = store.list_lifecycles()
        for lifecycle in lifecycles:
            print(f"  lifecycle {lifecycle.instrument_id}: {lifecycle.state.value}")
        account = store.get_account(config.account_id)
        if account is not None:
            print(
                f"  account: balance={account.balance} equity={account.equity} "
                f"realized={account.realized_pnl}"
            )
        reviews = posttrade_store.list_reviews()
        print(f"post-trade reviews recorded: {len(reviews)}")
        for review in reviews:
            print(
                f"  review {review.review_id} {review.instrument_id}: "
                f"{review.verdict} net={review.metrics.pnl_net} "
                f"artifact={review.artifact_key} vault={review.vault_path}"
            )
        return 0

    runner.serve()
    return 0


def _instrument(config: object, instrument_id: str, clock: object) -> Instrument:
    from apps.worker.config import make_instrument

    return make_instrument(config.instruments[instrument_id], clock.now())  # type: ignore[attr-defined]


if __name__ == "__main__":
    sys.exit(main())
