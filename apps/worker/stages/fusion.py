"""Signal Fusion stage (Phase 7).

Consumes ``research.bundle.created`` and fuses the bundled quant / LLM /
regime / memory inputs through the deterministic :class:`FusionEngine`
(INV-16). A FLAT fused signal completes the trace without a proposal —
nothing trades on noise.
"""

from __future__ import annotations

from core.domain.enums import PipelineStageName, SignalDirection, TradeLifecycleState
from core.schemas.events import DomainEvent
from core.schemas.fusion import FusionInputs, ResearchBundle
from core.schemas.signals import FusedSignal

from apps.worker.lifecycle import transition
from apps.worker.stages.base import Stage, StageRuntime

__all__ = ["FusionStage"]

_PRODUCER = "apps.worker.fusion"


class FusionStage(Stage):
    name = PipelineStageName.FUSION
    consumes = ("research.bundle.created",)
    producer = _PRODUCER

    def process(self, rt: StageRuntime, event: DomainEvent) -> list[DomainEvent]:
        bundle = ResearchBundle.model_validate(event.payload)
        trace_id = event.trace_id
        assert trace_id is not None
        engine = rt.extras["fusion_engine"]
        fused: FusedSignal | None = engine.fuse(
            FusionInputs(
                quant=bundle.quant, llm=bundle.llm, regime=bundle.regime, memory=bundle.memory
            )
        )
        with rt.telemetry.observation(
            trace_id=trace_id,
            name="signal_fusion.metadata",
            as_type="chain",
            metadata={
                "component": "signal_fusion",
                "version": fused.calibration_version if fused is not None else "unknown",
                "instrument_id": bundle.instrument_id,
            },
            input={
                "available": [
                    name
                    for name in ("quant", "llm", "regime", "memory")
                    if getattr(bundle, name) is not None
                ]
            },
        ) as observation:
            observation.update(
                output=(
                    {
                        "direction": fused.direction.value,
                        "confidence": fused.confidence,
                        "components": [
                            component.model_dump(mode="json") for component in fused.components
                        ],
                        "calibration_version": fused.calibration_version,
                    }
                    if fused is not None
                    else {"result": "no_signal"}
                )
            )
        if fused is None:
            transition(
                rt,
                trace_id,
                TradeLifecycleState.SIGNAL_FUSED,
                fields={"error": "no fusion inputs available"},
            )
            return []
        transition(rt, trace_id, TradeLifecycleState.SIGNAL_FUSED)
        rt.store.save_context_fragment(
            trace_id,
            "fused",
            fused.canonical_dict(),
            instrument_id=bundle.instrument_id,
            updated_at=rt.clock.now(),
        )
        if fused.direction is SignalDirection.FLAT:
            rt.audit.record(
                "signal.fused.flat",
                target=bundle.instrument_id,
                trace_id=trace_id,
                metadata={"strength": fused.fused_strength},
            )
            return []
        return [self.make_event(rt, "signal.fused", fused, trace_id=trace_id)]
