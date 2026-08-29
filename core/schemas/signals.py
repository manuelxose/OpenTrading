"""Signal contracts: ``QuantSignal``, ``LLMSignal``, ``FusedSignal``."""

from __future__ import annotations

import math
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from core.domain.enums import SignalDirection
from core.schemas.base import BaseContractModel, DomainObject, UtcDateTime
from core.schemas.research import EvidenceRef

__all__ = [
    "CommitteeMember",
    "DisagreementRecord",
    "FusedSignal",
    "LLMSignal",
    "QuantSignal",
    "SignalComponent",
]


class QuantSignal(DomainObject):
    """Deterministic quantitative signal (Qlib models, Phase 2+)."""

    signal_id: UUID
    instrument_id: str = Field(min_length=1)
    direction: SignalDirection
    strength: float = Field(ge=0, le=1)
    score: float | None = None
    confidence: float = Field(ge=0, le=1)
    horizon_seconds: int | None = Field(default=None, ge=0)
    expected_return: float | None = None
    model_id: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    feature_version: str | None = None
    as_of: UtcDateTime


class CommitteeMember(BaseContractModel):
    """One analyst in the TradingAgents qualitative committee (Phase 2+)."""

    name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    stance: SignalDirection
    argument: str = Field(min_length=1)
    weight: float = Field(default=1.0, ge=0, le=1)


class LLMSignal(DomainObject):
    """Advisory qualitative signal. Advisory only — never orders, never sizing (INV-1)."""

    signal_id: UUID
    instrument_id: str = Field(min_length=1)
    direction: SignalDirection
    strength: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    reasoning: str = Field(min_length=1)
    committee: list[CommitteeMember] = Field(min_length=1)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    model_name: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    as_of: UtcDateTime
    cost_usd: float | None = Field(default=None, ge=0)
    latency_ms: int | None = Field(default=None, ge=0)


class SignalComponent(BaseContractModel):
    """One fused input (quant / llm / regime / memory) with calibrated weight.

    ``score`` is a *signed* contribution in [-1, 1]: positive votes LONG,
    negative votes SHORT, zero abstains (FLAT). ``weight`` is the calibrated,
    normalized share; the components of one ``FusedSignal`` sum to 1.0.

    The direction is derived from the sign of ``score`` (see
    :meth:`direction`), so a component can never contradict itself.
    """

    name: str = Field(min_length=1)
    score: float = Field(ge=-1, le=1, allow_inf_nan=False)
    weight: float = Field(ge=0, le=1, allow_inf_nan=False)

    @property
    def direction(self) -> SignalDirection:
        if self.score > 0:
            return SignalDirection.LONG
        if self.score < 0:
            return SignalDirection.SHORT
        return SignalDirection.FLAT


class DisagreementRecord(BaseContractModel):
    """One recorded conflict between directional inputs and the policy applied
    (INV-16). Carried on the ``FusedSignal`` so downstream consumers can see
    when — and how — inputs disagreed, without the fusion engine hiding it."""

    components: list[str] = Field(min_length=2)
    policy_applied: str = Field(min_length=1)
    detail: str | None = None


class FusedSignal(DomainObject):
    """Signal Fusion output (INV-16). Weights derive from historical calibration,
    never from arbitrary choice; baselines are always compared.

    Semantics: the fused direction is the sign of the weighted sum of the
    (signed) component scores; ``fused_strength`` is its absolute value. A FLAT
    signal has exactly zero net score and zero strength.
    """

    signal_id: UUID
    instrument_id: str = Field(min_length=1)
    direction: SignalDirection
    fused_strength: float = Field(ge=0, le=1, allow_inf_nan=False)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    components: list[SignalComponent] = Field(min_length=1)
    calibration_version: str = Field(min_length=1)
    calibration_notes: str | None = None
    compared_against: list[str] = Field(
        default_factory=list,
        description="Baselines compared during calibration, e.g. quant_only, llm_only (INV-16)",
    )
    missing_inputs: list[str] = Field(
        default_factory=list,
        description="Expected inputs absent at fusion time, e.g. ['llm']",
    )
    disagreements: list[DisagreementRecord] = Field(default_factory=list)
    as_of: UtcDateTime

    @model_validator(mode="after")
    def _check_weights(self) -> Self:
        total = sum(component.weight for component in self.components)
        if not math.isclose(total, 1.0, abs_tol=1e-9):
            raise ValueError("component weights must sum to 1.0")
        net = sum(component.score * component.weight for component in self.components)
        if not math.isclose(abs(net), self.fused_strength, abs_tol=1e-9):
            raise ValueError(
                "fused_strength must equal the absolute weighted sum of component scores"
            )
        if net > 0 and self.direction is not SignalDirection.LONG:
            raise ValueError("positive net score requires direction LONG")
        if net < 0 and self.direction is not SignalDirection.SHORT:
            raise ValueError("negative net score requires direction SHORT")
        if math.isclose(net, 0.0, abs_tol=1e-9) and (
            self.direction is not SignalDirection.FLAT
            or not math.isclose(self.fused_strength, 0.0, abs_tol=1e-9)
        ):
            raise ValueError("a FLAT fused signal requires zero net score and zero strength")
        return self
