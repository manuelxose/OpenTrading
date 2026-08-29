"""Signal Fusion input contracts (INV-16, Phase 7).

The fusion engine fuses up to four inputs into ``core.schemas.FusedSignal``:

- ``QuantSignal`` — deterministic quantitative signal (already in ``signals.py``)
- ``LLMSignal`` — advisory qualitative signal (already in ``signals.py``)
- ``RegimeContext`` — market-regime classifier output
- ``MemoryContext`` — memory-derived stance (Graphiti temporal memory)

These context contracts are advisory inputs: they never order, never size,
never change risk limits (INV-1). ``FusionInputs`` is the one bundle the
engine accepts, so each upstream producer is replaceable without touching the
engine.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import Field

from core.domain.enums import SignalDirection
from core.schemas.base import BaseContractModel, DomainObject, UtcDateTime
from core.schemas.research import EvidenceRef
from core.schemas.signals import LLMSignal, QuantSignal

__all__ = [
    "FusionInputs",
    "MemoryContext",
    "RegimeContext",
    "ResearchBundle",
]

#: Canonical input names in engine order (used for deterministic loops).
INPUT_NAMES: tuple[str, ...] = ("quant", "llm", "regime", "memory")


class RegimeContext(BaseContractModel):
    """Market-regime classifier output (architecture §16 regime testing).

    ``direction`` / ``score`` is the regime model's directional tilt for the
    instrument; ``confidence`` is the classifier's own confidence.
    """

    regime: str = Field(min_length=1, description="Regime label, e.g. trend_up, range, vol_crisis")
    direction: SignalDirection
    score: float = Field(ge=0, le=1, allow_inf_nan=False)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    classifier_version: str = Field(min_length=1)
    source: str = Field(min_length=1, description="Producing component, e.g. engines.regime.v1")
    as_of: UtcDateTime


class MemoryContext(BaseContractModel):
    """Memory-derived stance from the temporal memory (Graphiti, INV-3, INV-11).

    A distilled stance over point-in-time memory evidence for the instrument.
    ``evidence_refs`` keep the result auditable back to its episodes.
    """

    direction: SignalDirection
    score: float = Field(ge=0, le=1, allow_inf_nan=False)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    summary: str = Field(default="", description="Human-readable distillation of the evidence")
    memory_version: str = Field(min_length=1)
    source: str = Field(min_length=1, description="Producing component, e.g. engines.memory.v1")
    as_of: UtcDateTime


class FusionInputs(BaseContractModel):
    """All fusion inputs for one instrument at one point in time.

    Any input may be absent (``None``); the engine's missing-signal policy
    decides how absence is handled. All timestamps must be UTC and, for live
    fusion, never posterior to the evaluation time (INV-3).
    """

    quant: QuantSignal | None = None
    llm: LLMSignal | None = None
    regime: RegimeContext | None = None
    memory: MemoryContext | None = None

    def available(self) -> list[str]:
        """Names of the inputs that are present, in canonical engine order."""
        return [name for name in INPUT_NAMES if getattr(self, name) is not None]


class ResearchBundle(DomainObject):
    """Everything the research stage produced for one instrument at one point
    in time (Phase 7): quant, LLM, memory and regime inputs in a single payload.

    A failed LLM analysis leaves ``llm`` as ``None`` and ``llm_error`` populated
    — the bundle still flows to fusion, which applies its missing-signal policy
    (INV-1: a failed LLM analysis must never break account state).
    """

    bundle_id: UUID
    instrument_id: str = Field(min_length=1)
    snapshot_ref: str = Field(min_length=1, description="Canonical snapshot source id")
    quant: QuantSignal | None = None
    llm: LLMSignal | None = None
    memory: MemoryContext | None = None
    regime: RegimeContext | None = None
    llm_error: str | None = None
    as_of: UtcDateTime
