"""Fusion configuration: component weights, policies and confidence maps (INV-16).

Weights are stored as *integer basis points* (0..10000, sum exactly 10000) so a
configuration is exact, hashable and deterministic — never subject to float
accumulation. Confidence calibration is stored as piecewise-linear
:class:`ConfidenceMap` breakpoints learned from labeled history.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Self

from core.schemas.base import BaseContractModel
from core.schemas.fusion import INPUT_NAMES
from pydantic import Field, model_validator

__all__ = [
    "COMPONENT_NAMES",
    "ComponentWeights",
    "ConfidenceMap",
    "DisagreementPolicy",
    "FusionConfig",
    "MissingSignalPolicy",
]

#: Canonical component order — every deterministic loop iterates in this order.
COMPONENT_NAMES: tuple[str, ...] = INPUT_NAMES

#: Baselines every calibrated configuration is compared against (INV-16).
DEFAULT_BASELINES: tuple[str, ...] = ("quant_only", "llm_only", "quant_plus_llm", "baseline")


class DisagreementPolicy(StrEnum):
    """How conflicting directional inputs are resolved (INV-16)."""

    NEUTRALIZE = "NEUTRALIZE"
    """Linear combination; opposing scores cancel honestly (default)."""

    TRUST_HIGHER_CONFIDENCE = "TRUST_HIGHER_CONFIDENCE"
    """The disagreeing component with the highest calibrated confidence decides;
    the others abstain (score 0)."""

    REQUIRE_CONSENSUS = "REQUIRE_CONSENSUS"
    """Any directional conflict suppresses the signal: all directional
    components abstain and the fused signal is FLAT."""


class MissingSignalPolicy(StrEnum):
    """How absent inputs are handled (INV-16)."""

    RENORMALIZE = "RENORMALIZE"
    """Weights of the present inputs are renormalized to sum to 1 (default)."""

    REQUIRE_QUANT = "REQUIRE_QUANT"
    """A missing QuantSignal means no fused signal at all (fusion returns None)."""


class ComponentWeights(BaseContractModel):
    """Calibrated shares per input in basis points (sum must equal 10000)."""

    quant_bp: int = Field(ge=0, le=10000)
    llm_bp: int = Field(ge=0, le=10000)
    regime_bp: int = Field(ge=0, le=10000)
    memory_bp: int = Field(ge=0, le=10000)

    @model_validator(mode="after")
    def _check_sum(self) -> Self:
        if self.quant_bp + self.llm_bp + self.regime_bp + self.memory_bp != 10000:
            raise ValueError("component weights in basis points must sum to exactly 10000")
        return self

    def bp_for(self, name: str) -> int:
        return int(getattr(self, f"{name}_bp"))

    def as_dict(self) -> dict[str, int]:
        return {name: self.bp_for(name) for name in COMPONENT_NAMES}

    @classmethod
    def from_dict(cls, bp: dict[str, int]) -> ComponentWeights:
        return cls(
            quant_bp=bp["quant"],
            llm_bp=bp["llm"],
            regime_bp=bp["regime"],
            memory_bp=bp["memory"],
        )


class ConfidenceMap(BaseContractModel):
    """Piecewise-linear mapping from raw confidence to calibrated confidence.

    ``x`` is strictly increasing raw-confidence breakpoints; ``y`` the
    calibrated values at those breakpoints. Evaluation is linear interpolation
    with constant extrapolation (clamped to the endpoints). An empty map is the
    identity mapping.
    """

    x: list[float]
    y: list[float]

    @model_validator(mode="after")
    def _check_shape(self) -> Self:
        if len(self.x) != len(self.y):
            raise ValueError("x and y must have the same length")
        if len(self.x) > 1 and any(a >= b for a, b in zip(self.x, self.x[1:], strict=True)):
            raise ValueError("x breakpoints must be strictly increasing")
        if any(value < 0 or value > 1 for value in self.y):
            raise ValueError("calibrated confidence values must be in [0, 1]")
        return self

    def map(self, raw: float) -> float:
        """Map one raw confidence through the calibrated curve."""
        if not self.x:
            return raw
        if raw <= self.x[0]:
            return self.y[0]
        if raw >= self.x[-1]:
            return self.y[-1]
        for i, (lo, hi) in enumerate(zip(self.x, self.x[1:], strict=True)):
            if lo <= raw <= hi:
                if hi == lo:
                    return self.y[i]
                ratio = (raw - lo) / (hi - lo)
                return self.y[i] + ratio * (self.y[i + 1] - self.y[i])
        raise AssertionError("unreachable: breakpoints do not cover the raw value")


class FusionConfig(BaseContractModel):
    """Deterministic fusion configuration.

    - ``default_weights``: calibrated weights used when no regime-specific
      weight set applies.
    - ``regime_weights``: per-regime calibrated weights (regime-specific
      models); regimes without an entry fall back to ``default_weights``.
    - ``confidence_calibration``: per-producer ``ConfidenceMap`` keyed by
      ``"<component>:<producer_key>"`` (e.g. ``"quant:model-01"``).
    - ``version``: the calibration version this config was produced by.
    """

    name: str = Field(min_length=1)
    version: str = Field(default="uncalibrated", min_length=1)
    default_weights: ComponentWeights
    regime_weights: dict[str, ComponentWeights] = Field(default_factory=dict)
    confidence_calibration: dict[str, ConfidenceMap] = Field(default_factory=dict)
    disagreement_policy: DisagreementPolicy = DisagreementPolicy.NEUTRALIZE
    missing_policy: MissingSignalPolicy = MissingSignalPolicy.RENORMALIZE
    flat_threshold: float = Field(default=0.0, ge=0, le=1)
    compared_against: list[str] = Field(default_factory=lambda: list(DEFAULT_BASELINES))
    notes: str | None = None

    @model_validator(mode="after")
    def _require_calibrated_version(self) -> Self:
        """INV-16: weights must derive from historical calibration. A config
        that never went through the calibration engine is rejected rather than
        silently traded with arbitrary weights."""
        if self.version == "uncalibrated":
            raise ValueError(
                "fusion configs must be calibrated (INV-16): version "
                "'uncalibrated' is not executable — run the calibration engine "
                "or load a signed CalibrationArtifact"
            )
        return self

    def weights_for_regime(self, regime: str | None) -> ComponentWeights:
        if regime is not None and regime in self.regime_weights:
            return self.regime_weights[regime]
        return self.default_weights

    def calibrated_confidence(self, component: str, producer_key: str, raw: float) -> float:
        """Calibrate a raw confidence; unknown producers keep their raw value."""
        calibration = self.confidence_calibration.get(f"{component}:{producer_key}")
        if calibration is None:
            return raw
        return calibration.map(raw)
