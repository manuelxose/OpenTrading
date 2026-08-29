"""Stage framework for the autonomous pipeline (Phase 7).

Every stage:

- declares which canonical events it consumes;
- is idempotent per ``(trace_id, stage)`` through the pipeline store — a
  redelivery after a worker restart is a no-op once the stage has succeeded;
- records a :class:`PipelineRunRecord` for every attempt (RUNNING → SUCCEEDED /
  FAILED), so PostgreSQL alone reconstructs exactly where a trace stopped;
- propagates ``trace_id`` into every payload it produces;
- expected domain failures (LLM timeout, TradingAgents crash, venue reject)
  are handled inside the stage; unexpected failures propagate to the worker
  loop, which retries and eventually dead-letters the message.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from core.audit.audit import AuditLogger
from core.clock.clocks import Clock
from core.domain.enums import PipelineStageName, PipelineStatus
from core.events.envelope import build_domain_event
from core.observability.metrics import OperationalMetrics, metrics
from core.observability.tracing import LangfuseTracer, tracer
from core.schemas.base import DomainObject, Provenance
from core.schemas.events import DomainEvent
from core.schemas.pipeline import PipelineRunRecord

from apps.worker.persistence import PipelineStore

__all__ = ["Stage", "StageRuntime"]

logger = logging.getLogger(__name__)


class EventPublisher(Protocol):
    def publish(self, event: DomainEvent) -> str: ...


@dataclass
class StageRuntime:
    """Shared collaborators handed to every stage (plain container)."""

    store: PipelineStore
    publisher: EventPublisher
    clock: Clock
    audit: AuditLogger
    config: Any
    instruments: dict[str, Any]
    policy: Any
    execution_store: Any
    ledger: Any
    snapshot_cache: dict[tuple[str, int], Any] = field(default_factory=dict)
    latest_snapshots: dict[str, Any] = field(default_factory=dict)
    extras: dict[str, Any] = field(default_factory=dict)
    telemetry: LangfuseTracer = field(default_factory=lambda: tracer)
    operational_metrics: OperationalMetrics = field(default_factory=lambda: metrics)

    # ── helpers stages share ──────────────────────────────────────────────────

    def snapshot_for(self, instrument_id: str, step: int, now: datetime) -> Any:
        """Cached point-in-time snapshot for (instrument, step)."""
        key = (instrument_id, step)
        if key in self.snapshot_cache:
            return self.snapshot_cache[key]
        source = self.extras["snapshot_source"]
        snapshot = source.latest(instrument_id, now=now, step=step)
        self.snapshot_cache[key] = snapshot
        return snapshot

    def last_snapshot(self, instrument_id: str) -> Any | None:
        """Most recent snapshot for an instrument (latest_snapshots first)."""
        latest = self.latest_snapshots.get(instrument_id)
        if latest is not None:
            return latest
        for (iid, _step), snapshot in reversed(list(self.snapshot_cache.items())):
            if iid == instrument_id:
                return snapshot
        return None

    def provenance(self, producer: str, produced_at: datetime) -> Provenance:
        return Provenance(producer=producer, produced_at=produced_at)


class Stage:
    """Base class for pipeline stages: idempotent, recorded, trace-propagating."""

    name: PipelineStageName
    consumes: tuple[str, ...] = ()
    producer: str = "apps.worker"

    def accepts(self, event_name: str) -> bool:
        return event_name in self.consumes

    # ── public entry (called by the worker loop) ──────────────────────────────

    def handle(self, rt: StageRuntime, event: DomainEvent) -> list[DomainEvent]:
        trace_id = event.trace_id
        if trace_id is None:
            logger.warning("%s: dropping event %s without trace_id", self.name, event.event_name)
            return []
        if rt.store.has_succeeded(trace_id, self.name):
            return []  # already done (restart redelivery)
        now = rt.clock.now()
        attempt = self._next_attempt(rt, trace_id)
        rt.store.save_run(
            PipelineRunRecord(
                run_id=uuid4(),
                trace_id=trace_id,
                cycle_id=self._cycle_of(event),
                instrument_id=self._instrument_of(event),
                stage=self.name,
                status=PipelineStatus.RUNNING,
                attempt=attempt,
                started_at=now,
            )
        )
        began = time.perf_counter()
        try:
            with rt.telemetry.observation(
                trace_id=self._telemetry_trace_id(rt, trace_id),
                name=f"pipeline.{self.name.value.lower()}",
                as_type="agent" if self.name is PipelineStageName.RESEARCH else "span",
                metadata={
                    "stage": self.name.value,
                    "event": event.event_name,
                    "attempt": attempt,
                    "instrument_id": self._instrument_of(event),
                },
                input={"event_name": event.event_name, "event_id": str(event.event_id)},
            ) as observation:
                outputs = self.process(rt, event)
                observation.update(
                    output={"events": [output.event_name for output in outputs]},
                    metadata={"status": "ok"},
                )
        except Exception as exc:
            duration = time.perf_counter() - began
            rt.operational_metrics.pipeline_stage_duration.labels(
                stage=self.name.value, status="error"
            ).observe(duration)
            rt.operational_metrics.pipeline_errors.labels(
                stage=self.name.value, error_type=type(exc).__name__
            ).inc()
            rt.store.save_run(
                PipelineRunRecord(
                    run_id=uuid4(),
                    trace_id=trace_id,
                    cycle_id=self._cycle_of(event),
                    instrument_id=self._instrument_of(event),
                    stage=self.name,
                    status=PipelineStatus.FAILED,
                    attempt=attempt,
                    started_at=now,
                    completed_at=rt.clock.now(),
                    error=f"{type(exc).__name__}: {exc}"[:2000],
                )
            )
            rt.audit.record(
                "pipeline.stage.failed",
                target=f"{self.name.value}:{trace_id}",
                trace_id=trace_id,
                outcome="ERROR",
                metadata={"error": type(exc).__name__, "event": event.event_name},
            )
            raise
        rt.operational_metrics.pipeline_stage_duration.labels(
            stage=self.name.value, status="ok"
        ).observe(time.perf_counter() - began)
        # Publish outputs BEFORE recording SUCCEEDED: a crash mid-publish leaves
        # the message unacked, the stage re-runs (no SUCCEEDED yet) and the
        # outputs are re-published — at-least-once without silent loss.
        # Downstream stages deduplicate on (trace_id, stage), so the duplicate
        # copies published after a crash are no-ops there.
        for output in outputs:
            rt.publisher.publish(output)
        rt.store.save_run(
            PipelineRunRecord(
                run_id=uuid4(),
                trace_id=trace_id,
                cycle_id=self._cycle_of(event),
                instrument_id=self._instrument_of(event),
                stage=self.name,
                status=PipelineStatus.SUCCEEDED,
                attempt=attempt,
                started_at=now,
                completed_at=rt.clock.now(),
                output_refs=self._output_refs(outputs),
            )
        )
        return outputs

    @staticmethod
    def _telemetry_trace_id(rt: StageRuntime, trace_id: UUID) -> UUID:
        """Resolve the durable trade trace while preserving domain idempotency IDs."""
        context = rt.store.get_context(trace_id)
        if context is None:
            return trace_id
        raw = context.fragments.get("telemetry", {}).get("trade_trace_id")
        try:
            return UUID(str(raw)) if raw is not None else trace_id
        except ValueError:
            return trace_id

    # ── hooks ──────────────────────────────────────────────────────────────────

    def process(self, rt: StageRuntime, event: DomainEvent) -> list[DomainEvent]:
        """Stage-specific logic; returns events to publish (trace set by caller)."""
        raise NotImplementedError

    def _next_attempt(self, rt: StageRuntime, trace_id: UUID) -> int:
        existing = rt.store.get_run(trace_id, self.name)
        if existing is None:
            return 1
        return existing.attempt + 1

    @staticmethod
    def _cycle_of(event: DomainEvent) -> str:
        payload = event.payload
        for key in ("cycle_id", "context"):
            value = payload.get(key)
            if isinstance(value, str) and key == "cycle_id":
                return value
            if isinstance(value, dict) and value.get("cycle_id"):
                return str(value["cycle_id"])
        return "manual"

    @staticmethod
    def _instrument_of(event: DomainEvent) -> str:
        payload = event.payload
        value = payload.get("instrument_id")
        if isinstance(value, str) and value:
            return value
        context = payload.get("context")
        if isinstance(context, dict):
            value = context.get("instrument_id")
            if isinstance(value, str) and value:
                return value
        return "-"

    @staticmethod
    def _output_refs(outputs: list[DomainEvent]) -> dict[str, str]:
        refs: dict[str, str] = {}
        for event in outputs:
            payload = event.payload
            for key in (
                "proposal_id",
                "decision_id",
                "signal_id",
                "bundle_id",
                "order_intent_id",
                "trade_id",
                "review_id",
                "episode_id",
                "execution_report_id",
                "request_id",
            ):
                value = payload.get(key)
                if isinstance(value, str) and value:
                    refs[key] = value
                    break
        return refs

    # ── event construction helpers ────────────────────────────────────────────

    def make_event(
        self,
        rt: StageRuntime,
        event_name: str,
        payload: DomainObject,
        *,
        trace_id: UUID,
    ) -> DomainEvent:
        return build_domain_event(
            event_name=event_name,
            payload=payload,
            clock=rt.clock,
            producer=self.producer,
            trace_id=trace_id,
        )
