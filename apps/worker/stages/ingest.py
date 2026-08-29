"""Ingest orchestrator: starts one research cycle (Phase 7 entry point).

Not a stream consumer — it is invoked by the scheduler/CLI for each watchlist
instrument every cycle. It:

1. fetches the point-in-time :class:`MarketSnapshot`;
2. creates the trace id and the :class:`TradeLifecycle` (RESEARCHING);
3. publishes ``market.snapshot.created`` and ``research.requested`` on the bus
   with the shared trace id.

Everything downstream reacts to those two events; a crash here loses nothing
because nothing has been published yet.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4, uuid5

from core.domain.enums import PipelineStageName, PipelineStatus, TradeLifecycleState
from core.schemas import ResearchRequest
from core.schemas.base import Provenance
from core.schemas.events import DomainEvent
from core.schemas.pipeline import PipelineRunRecord, TradeLifecycle

from apps.worker.stages.base import StageRuntime

__all__ = ["IngestOrchestrator"]

_PRODUCER = "apps.worker.ingest"

#: Fixed namespace for deterministic request ids.
_REQUEST_NS = UUID("3d9f6a1b-5c2e-4f7a-9b8d-0e1c2d3e4f5a")


class IngestOrchestrator:
    """Starts one pipeline trace per instrument cycle."""

    def __init__(self, rt: StageRuntime) -> None:
        self._rt = rt

    def start_cycle(
        self, instrument_id: str, *, step: int, now: datetime
    ) -> tuple[DomainEvent, ...]:
        rt = self._rt
        trace_id = uuid4()
        cycle_id = f"cycle-{step}"
        snapshot = rt.snapshot_for(instrument_id, step, now)
        rt.latest_snapshots[instrument_id] = snapshot
        config = rt.config

        lifecycle_id = uuid5(_REQUEST_NS, str(trace_id))
        rt.store.save_lifecycle(
            TradeLifecycle(
                lifecycle_id=lifecycle_id,
                trace_id=trace_id,
                strategy_id=config.strategy_id,
                strategy_version=config.strategy_version,
                instrument_id=instrument_id,
                state=TradeLifecycleState.RESEARCHING,
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
        rt.store.save_context_fragment(
            trace_id,
            "source_data",
            snapshot.model_dump(mode="json"),
            instrument_id=instrument_id,
            updated_at=now,
        )

        request = ResearchRequest(
            request_id=uuid5(_REQUEST_NS, f"{instrument_id}:{cycle_id}"),
            title=f"Autonomous PAPER research: {instrument_id}",
            question=f"What is the directional outlook for {instrument_id}?",
            scope=[instrument_id],
            requested_by="paper-scheduler",
            priority=3,
            context={
                "instrument_id": instrument_id,
                "cycle_id": cycle_id,
                "step": step,
            },
            trace_id=trace_id,
            produced_at=now,
            provenance=Provenance(producer=_PRODUCER, produced_at=now),
        )

        snapshot_event = self._event("market.snapshot.created", snapshot, trace_id)
        request_event = self._event("research.requested", request, trace_id)

        rt.store.save_run(
            PipelineRunRecord(
                run_id=uuid4(),
                trace_id=trace_id,
                cycle_id=cycle_id,
                instrument_id=instrument_id,
                stage=PipelineStageName.INGEST,
                status=PipelineStatus.SUCCEEDED,
                attempt=1,
                started_at=now,
                completed_at=now,
                input_refs={},
                output_refs={
                    "request_id": str(request.request_id),
                    "snapshot_source": snapshot.source,
                },
            )
        )
        return snapshot_event, request_event

    def _event(self, event_name: str, payload: object, trace_id: UUID) -> DomainEvent:
        from core.events.envelope import build_domain_event

        return build_domain_event(
            event_name=event_name,
            payload=payload,  # type: ignore[arg-type]
            clock=self._rt.clock,
            producer=_PRODUCER,
            trace_id=trace_id,
        )
