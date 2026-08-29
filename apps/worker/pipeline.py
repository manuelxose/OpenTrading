"""Pipeline assembly and the Redis Streams worker loop (Phase 7).

``build_paper_runtime`` wires every collaborator into a :class:`StageRuntime`
(adapters, engines, stores, ledger). ``StageWorker`` runs one consumer group
against the shared stream:

- startup recovery: reclaim PEL entries (XAUTOCLAIM) so messages left unacked
  by a crashed worker are reprocessed; poisoned messages exceeding
  ``max_deliveries`` are archived to the dead-letter stream;
- the main loop reads new messages, dispatches them to the matching stages,
  publishes each stage's outputs, and ACKs;
- a failed handler leaves the message unacked — it is redelivered after the
  claim-idle window, so stage idempotency (pipeline store) makes retries safe.

Trace propagation: every published output event carries the consuming event's
``trace_id`` (enforced by :class:`Stage.handle`).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from core.audit.audit import AuditLogger, InMemoryAuditSink
from core.clock.clocks import Clock, SystemClock
from core.schemas import Instrument
from core.schemas.events import DomainEvent
from engines.signal_fusion.config import FusionConfig

from apps.worker.bus import InMemoryStreamBus, RedisStreamBus
from apps.worker.persistence import PipelineStore
from apps.worker.stages.accounting import AccountingStage
from apps.worker.stages.base import Stage, StageRuntime
from apps.worker.stages.execution import PaperExecutionStage
from apps.worker.stages.fusion import FusionStage
from apps.worker.stages.order_intent import OrderIntentStage
from apps.worker.stages.positions import PositionsStage
from apps.worker.stages.posttrade import PosttradeStage
from apps.worker.stages.proposal import ProposalStage
from apps.worker.stages.research import ResearchStage
from apps.worker.stages.risk import RiskStage

__all__ = [
    "ALL_STAGES",
    "PaperPipeline",
    "StageWorker",
    "build_paper_runtime",
]

logger = logging.getLogger(__name__)

ALL_STAGES: tuple[type[Stage], ...] = (
    ResearchStage,
    FusionStage,
    ProposalStage,
    RiskStage,
    OrderIntentStage,
    PaperExecutionStage,
    PositionsStage,
    AccountingStage,
    PosttradeStage,
)


class PaperPipeline:
    """Stage graph: event name → stages that consume it."""

    def __init__(self, stages: list[Stage]) -> None:
        self._by_event: dict[str, list[Stage]] = {}
        self._groups: dict[str, list[Stage]] = {}
        for stage in stages:
            group = f"paper:{stage.name.value.lower()}"
            self._groups.setdefault(group, []).append(stage)
            for event_name in stage.consumes:
                self._by_event.setdefault(event_name, []).append(stage)

    def stages_for(self, event_name: str) -> list[Stage]:
        return self._by_event.get(event_name, [])

    def worker_specs(self) -> list[tuple[str, list[Stage]]]:
        """Consumer-group name → stages, in pipeline order."""
        return list(self._groups.items())

    def dispatch(self, rt: StageRuntime, event: DomainEvent) -> list[DomainEvent]:
        """Synchronous dispatch for in-process runs (tests, run-once)."""
        outputs: list[DomainEvent] = []
        for stage in self.stages_for(event.event_name):
            outputs.extend(stage.handle(rt, event))
        return outputs


class StageWorker:
    """One consumer group: recovery loop + new-message loop (unattended)."""

    def __init__(
        self,
        *,
        group: str,
        consumer: str,
        stages: list[Stage],
        rt: StageRuntime,
        bus: object,
        clock: Clock | None = None,
    ) -> None:
        self._group = group
        self._consumer = consumer
        self._stages = stages
        self._rt = rt
        self._bus = bus
        self._clock = clock or SystemClock()

    @property
    def group(self) -> str:
        return self._group

    def start(self) -> None:
        self._bus.ensure_group(self._group)  # type: ignore[attr-defined]

    def recover(self) -> list[Any]:
        """Reclaim stale PEL entries; dead-letter poisoned ones. Returns
        the reclaimed messages for dispatch."""
        bus = self._bus
        pending = bus.pending(self._group)  # type: ignore[attr-defined]
        self._rt.operational_metrics.set_redis_lag(self._group, len(pending))
        reclaimed: list[Any] = []
        for entry in pending:
            if entry.delivery_count > self._rt.config.bus.max_deliveries:
                for message in bus.read_pending(self._group, self._consumer):  # type: ignore[attr-defined]
                    if message.message_id == entry.message_id:
                        bus.dead_letter(  # type: ignore[attr-defined]
                            self._group,
                            message,
                            f"exceeded {self._rt.config.bus.max_deliveries} deliveries",
                        )
                        logger.error(
                            "dead-lettered %s after %d deliveries",
                            entry.message_id,
                            entry.delivery_count,
                        )
                        break
                continue
            if entry.idle_ms >= self._rt.config.bus.claim_idle_ms:
                reclaimed.extend(
                    bus.claim_stale(  # type: ignore[attr-defined]
                        self._group,
                        self._consumer,
                        min_idle_ms=self._rt.config.bus.claim_idle_ms,
                        count=self._rt.config.bus.batch_size,
                    )
                )
        return reclaimed

    def read_new(self, *, block_ms: int) -> list[Any]:
        return self._bus.read_new(  # type: ignore[attr-defined,no-any-return]
            self._group,
            self._consumer,
            count=self._rt.config.bus.batch_size,
            block_ms=block_ms,
        )

    def handle_message(self, message: object) -> bool:
        """Dispatch one message; ACK on success, leave unacked on failure.

        Stages publish their own outputs (before recording SUCCEEDED — see
        :class:`apps.worker.stages.base.Stage`), so this loop only ACKs.
        """
        event = message.event  # type: ignore[attr-defined]
        matched = False
        for stage in self._stages:
            if not stage.accepts(event.event_name):
                continue
            matched = True
            stage.handle(self._rt, event)
        self._bus.ack(self._group, message.message_id)  # type: ignore[attr-defined]
        if not matched:
            logger.debug("%s: no stage for %s", self._group, event.event_name)
        return matched

    def run_iteration(self) -> tuple[int, int]:
        """One pass: recover, then read+dispatch new messages. Returns
        (reclaimed, processed)."""
        reclaimed_messages = self.recover()
        messages = list(reclaimed_messages) + list(
            self.read_new(block_ms=self._rt.config.bus.block_ms)
        )
        processed = 0
        for message in messages:
            try:
                self.handle_message(message)
                processed += 1
            except Exception as exc:
                logger.error(
                    "%s: failed processing %s (delivery %d): %s",
                    self._group,
                    message.message_id,
                    message.delivery_count,
                    exc,
                )
                # left unacked: redelivered after claim_idle_ms
        self._rt.operational_metrics.set_service_health("worker", True)
        return len(reclaimed_messages), processed


def build_paper_runtime(
    *,
    config: Any,
    store: PipelineStore,
    bus: Any,
    execution_store: Any,
    ledger: Any,
    snapshot_source: Any,
    tradingagents: Any | None = None,
    memory: Any | None = None,
    memory_producer: Any | None = None,
    paper_executor: Any | None = None,
    posttrade_store: Any | None = None,
    artifact_store: Any | None = None,
    vault_writer: Any | None = None,
    clock: Clock | None = None,
    audit: AuditLogger | None = None,
) -> StageRuntime:
    """Wire all collaborators into one :class:`StageRuntime`."""
    from adapters.obsidian import MemoryVaultWriter
    from engines.execution.applier import OrderStateApplier
    from engines.posttrade.artifacts import MemoryArtifactStore
    from engines.posttrade.persistence import InMemoryPostTradeStore
    from engines.signal_fusion.fusion import FusionEngine

    from apps.worker.config import make_paper_policy, strategy_configuration
    from apps.worker.producers import BaselineQuantProducer, MemoryContextProducer

    now_clock = clock or SystemClock()
    now = now_clock.now()
    currencies = {
        currency
        for spec in config.instruments.values()
        for currency in (spec.base_currency, spec.quote_currency)
    }
    policy = make_paper_policy(config.risk, now, currencies)
    instruments = {
        instrument_id: _make_instrument_at(config, instrument_id, now)
        for instrument_id in config.watchlist
    }
    applier = OrderStateApplier(execution_store, now_clock)
    quant_producer = BaselineQuantProducer(
        model_id=config.quant_model_id, model_version=config.quant_model_version
    )
    memory_producer = memory_producer or (
        MemoryContextProducer(
            memory=memory,
            version=config.memory_version,
            source="apps.worker",
            query_template=config.memory_query_template,
        )
        if memory is not None
        else None
    )
    fusion_engine = FusionEngine(config.fusion or _default_fusion(), clock=now_clock)
    audit_logger = audit or AuditLogger(InMemoryAuditSink(), now_clock)

    rt = StageRuntime(
        store=store,
        publisher=bus,
        clock=now_clock,
        audit=audit_logger,
        config=config,
        instruments=instruments,
        policy=policy,
        execution_store=execution_store,
        ledger=ledger,
        extras={
            "snapshot_source": snapshot_source,
            "applier": applier,
            "quant_producer": quant_producer,
            "memory_producer": memory_producer,
            "fusion_engine": fusion_engine,
            "tradingagents": tradingagents,
            "memory": memory,
            "paper_executor": paper_executor,
            "strategy_configuration": strategy_configuration(config, now),
            "posttrade_store": posttrade_store or InMemoryPostTradeStore(),
            "artifact_store": artifact_store or MemoryArtifactStore(),
            "vault_writer": vault_writer or MemoryVaultWriter(),
        },
    )
    return rt


def _default_fusion() -> FusionConfig:
    from apps.worker.config import paper_fusion_config

    return paper_fusion_config()


def _make_instrument_at(config: Any, instrument_id: str, now: datetime) -> Instrument:
    from apps.worker.config import make_instrument

    return make_instrument(config.instruments[instrument_id], now)


def build_inmemory_bus(clock: Clock | None = None) -> InMemoryStreamBus:
    return InMemoryStreamBus(clock=clock)


def build_redis_bus(url: str, config: Any) -> RedisStreamBus:
    return RedisStreamBus(
        url,
        stream_key=config.bus.stream_key,
        retry_base_seconds=config.bus.retry_base_seconds,
        retry_max_seconds=config.bus.retry_max_seconds,
        max_attempts=None,  # unattended: retry forever
    )
