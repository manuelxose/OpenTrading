"""Research stage: memory retrieval + TradingAgents + quant (Phase 7).

Consumes ``research.requested`` and produces one :class:`ResearchBundle`
carrying every fusion input. Failure containment (DoD: *a failed LLM analysis
must never break account state*):

- the TradingAgents call runs through the adapter's own timeout/retry budget;
- any :class:`TradingAgentsError` (timeout, crash, mapping) is caught here,
  recorded in the audit trail and carried as ``llm_error`` on the bundle —
  the bundle still flows to fusion with ``llm=None`` (missing-signal policy);
- when ``llm_required`` is configured, a failed LLM only skips *this* cycle
  (``SKIPPED`` run record) — it never touches account or position state.
"""

from __future__ import annotations

from uuid import uuid4

from core.domain.enums import PipelineStageName, PipelineStatus
from core.schemas import LLMSignal, ResearchPacket, ResearchRequest
from core.schemas.base import Provenance
from core.schemas.events import DomainEvent
from core.schemas.fusion import ResearchBundle
from core.schemas.pipeline import PipelineRunRecord
from core.schemas.research import EvidenceRef

from apps.worker.stages.base import Stage, StageRuntime

__all__ = ["ResearchStage"]

_PRODUCER = "apps.worker.research"

_LLM_ERRORS = ("TradingAgentsError", "TradingAgentsTimeoutError")


class ResearchStage(Stage):
    name = PipelineStageName.RESEARCH
    consumes = ("research.requested",)
    producer = _PRODUCER

    def process(self, rt: StageRuntime, event: DomainEvent) -> list[DomainEvent]:
        request = ResearchRequest.model_validate(event.payload)
        instrument_id = str(request.context.get("instrument_id", "-"))
        step = int(request.context.get("step", 0))
        now = rt.clock.now()
        trace_id = event.trace_id
        assert trace_id is not None
        snapshot = rt.snapshot_for(instrument_id, step, now)
        rt.latest_snapshots[instrument_id] = snapshot

        events: list[DomainEvent] = []

        # ── deterministic quant signal (never fails) ──────────────────────────
        quant_producer = rt.extras["quant_producer"]
        quant = quant_producer.produce(instrument_id, snapshot, trace_id=trace_id, produced_at=now)
        events.append(self.make_event(rt, "quant.signal.created", quant, trace_id=trace_id))
        rt.store.save_context_fragment(
            trace_id,
            "quant",
            quant.canonical_dict(),
            instrument_id=instrument_id,
            updated_at=now,
        )

        # ── point-in-time memory stance (INV-3) ──────────────────────────────
        memory_context = None
        memory_producer = rt.extras.get("memory_producer")
        if memory_producer is not None:
            try:
                memory_context = memory_producer.produce(
                    instrument_id, as_of=now, trace_id=trace_id, produced_at=now
                )
                if memory_context is not None:
                    rt.store.save_context_fragment(
                        trace_id,
                        "memory",
                        memory_context.model_dump(mode="json"),
                        instrument_id=instrument_id,
                        updated_at=now,
                    )
            except Exception as exc:  # memory failure never blocks the cycle
                rt.audit.record(
                    "memory.retrieval.failed",
                    target=instrument_id,
                    trace_id=trace_id,
                    outcome="ERROR",
                    metadata={"error": type(exc).__name__},
                )

        # ── TradingAgents (advisory; failures are contained) ──────────────────
        llm: LLMSignal | None = None
        llm_error: str | None = None
        adapter = rt.extras.get("tradingagents")
        if adapter is None or not rt.config.llm_enabled:
            llm_error = "llm disabled" if adapter is None else "llm disabled by config"
        else:
            try:
                llm = adapter.run(request, snapshot, trace_id=trace_id, now=now)
                events.append(self.make_event(rt, "llm.signal.created", llm, trace_id=trace_id))
                rt.store.save_context_fragment(
                    trace_id,
                    "llm",
                    llm.canonical_dict(),
                    instrument_id=instrument_id,
                    updated_at=now,
                )
            except Exception as exc:
                llm_error = f"{type(exc).__name__}: {exc}"[:1000]
                rt.audit.record(
                    "llm.analysis.failed",
                    target=instrument_id,
                    trace_id=trace_id,
                    outcome="ERROR",
                    metadata={
                        "error": type(exc).__name__,
                        "llm_required": rt.config.llm_required,
                    },
                )
                if rt.config.llm_required:
                    rt.store.save_run(
                        PipelineRunRecord(
                            run_id=uuid4(),
                            trace_id=trace_id,
                            cycle_id=str(request.context.get("cycle_id", "manual")),
                            instrument_id=instrument_id,
                            stage=self.name,
                            status=PipelineStatus.SKIPPED,
                            attempt=1,
                            started_at=now,
                            completed_at=now,
                            error=llm_error,
                        )
                    )
                    return events  # quant event only; no bundle, no trade

        # ── the bundle: one message carrying all fusion inputs ────────────────
        bundle = ResearchBundle(
            bundle_id=uuid4(),
            instrument_id=instrument_id,
            snapshot_ref=snapshot.source,
            quant=quant,
            llm=llm,
            memory=memory_context,
            regime=None,
            llm_error=llm_error,
            as_of=now,
            trace_id=trace_id,
            produced_at=now,
            provenance=Provenance(producer=_PRODUCER, produced_at=now),
        )
        events.append(self.make_event(rt, "research.bundle.created", bundle, trace_id=trace_id))

        evidence: list[EvidenceRef] = []
        summary_parts = [f"quant {quant.direction.value} {quant.strength:.3f}"]
        if llm is not None:
            summary_parts.append(f"llm {llm.direction.value} {llm.strength:.3f}")
        if memory_context is not None:
            summary_parts.append(
                f"memory {memory_context.direction.value} {memory_context.score:.3f}"
            )
            evidence.extend(memory_context.evidence_refs)
        packet = ResearchPacket(
            packet_id=uuid4(),
            request_id=request.request_id,
            summary="; ".join(summary_parts),
            findings=list(summary_parts),
            evidence=evidence,
            confidence=0.5,
            authors=[_PRODUCER],
            related_instruments=[instrument_id],
            trace_id=trace_id,
            produced_at=now,
            provenance=Provenance(producer=_PRODUCER, produced_at=now),
        )
        events.append(self.make_event(rt, "research.completed", packet, trace_id=trace_id))
        return events
