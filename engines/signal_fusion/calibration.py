"""Calibration: learn fusion weights and confidence maps from labeled history
(INV-16 — weights are calibrated, never arbitrary).

The calibrator:

1. learns per-producer confidence calibration via isotonic regression
   (raw confidence → realized directional hit rate);
2. learns component weights by deterministic grid search over basis points,
   maximizing mean directional return on the training cases;
3. learns regime-specific weights when a regime has enough cases, falling back
   to weights learned on all cases otherwise;
4. zeroes the LLM weight when ``quant_plus_llm`` does not beat ``quant_only``
   by at least ``min_improvement`` — the LLM gets zero weight if it adds no
   measurable value;
5. compares the mandatory baselines (quant_only / llm_only / quant_plus_llm /
   simple baseline) on the training set and stores everything in a
   :class:`CalibrationArtifact`.

Everything is deterministic: the same cases and hyperparameters produce the
same artifact, including the same ``calibration_version``.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any
from uuid import UUID, uuid5

from core.schemas.base import BaseContractModel, UtcDateTime
from pydantic import Field

from engines.signal_fusion.config import (
    COMPONENT_NAMES,
    DEFAULT_BASELINES,
    ComponentWeights,
    ConfidenceMap,
    DisagreementPolicy,
    FusionConfig,
    MissingSignalPolicy,
)
from engines.signal_fusion.errors import CalibrationInsufficientDataError
from engines.signal_fusion.evaluation import (
    ConfigMetrics,
    LabeledFusionCase,
    compute_cases_hash,
    evaluate_cases,
)
from engines.signal_fusion.fusion import (
    FUSION_ENGINE_VERSION,
    canonical_dumps,
    producer_keys,
    raw_confidences,
    signed_scores,
)
from engines.signal_fusion.isotonic import isotonic_regression

__all__ = ["CalibrationArtifact", "Calibrator", "DataScope", "calibrate"]

_CALIBRATION_NAMESPACE = UUID("8d4a1f6e-2b3c-4d5e-9a7f-0c8b2e4f6a1d")


class DataScope(BaseContractModel):
    """Auditable summary of the data a calibration was trained on."""

    n_cases: int = Field(ge=0)
    instrument_ids: list[str] = Field(default_factory=list)
    quant_models: list[str] = Field(default_factory=list)
    llm_models: list[str] = Field(default_factory=list)
    regime_labels: list[str] = Field(default_factory=list)
    as_of_from: UtcDateTime | None = None
    as_of_to: UtcDateTime | None = None


class CalibrationArtifact(BaseContractModel):
    """Complete, versioned output of a calibration run.

    Everything needed to reproduce a fused signal is inside ``config``; the
    metrics and notes are the evidence the weights are not arbitrary.
    """

    artifact_id: UUID
    calibration_version: str = Field(min_length=1)
    engine_version: str = Field(min_length=1)
    config: FusionConfig
    trained_at: UtcDateTime
    data_scope: DataScope
    train_metrics: list[ConfigMetrics]
    llm_added_value: bool
    llm_weight_bp: int = Field(ge=0, le=10000)
    selection_notes: list[str] = Field(default_factory=list)


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _weight_grid(units: int, n_components: int) -> list[tuple[int, ...]]:
    """All compositions of ``units`` into ``n_components`` non-negative parts,
    in deterministic order."""
    combos: list[tuple[int, ...]] = []

    def rec(remaining: int, parts: list[int]) -> None:
        if len(parts) == n_components - 1:
            combos.append((*parts, remaining))
            return
        for value in range(remaining + 1):
            rec(remaining - value, [*parts, value])

    rec(units, [])
    return combos


class Calibrator:
    """Deterministic calibration from labeled cases (INV-16)."""

    def __init__(
        self,
        *,
        weight_step_bp: int = 500,
        min_cases_per_regime: int = 20,
        min_cases_confidence: int = 10,
        min_improvement: float = 0.0,
        flat_threshold: float = 0.0,
        disagreement_policy: DisagreementPolicy = DisagreementPolicy.NEUTRALIZE,
        missing_policy: MissingSignalPolicy = MissingSignalPolicy.RENORMALIZE,
    ) -> None:
        if 10000 % weight_step_bp != 0 or weight_step_bp <= 0:
            raise CalibrationInsufficientDataError(
                f"weight_step_bp {weight_step_bp} must divide 10000 exactly"
            )
        self.weight_step_bp = weight_step_bp
        self.min_cases_per_regime = min_cases_per_regime
        self.min_cases_confidence = min_cases_confidence
        self.min_improvement = min_improvement
        self.flat_threshold = flat_threshold
        self.disagreement_policy = disagreement_policy
        self.missing_policy = missing_policy

    # -- confidence calibration -------------------------------------------

    def _confidence_maps(self, cases: list[LabeledFusionCase]) -> dict[str, ConfidenceMap]:
        grouped: dict[str, list[tuple[float, float]]] = {}
        for case in cases:
            keys = producer_keys(case.inputs)
            confidences = raw_confidences(case.inputs)
            scores = signed_scores(case.inputs)
            for name, key in keys.items():
                hit = (
                    1.0
                    if scores[name] != 0.0 and _sign(scores[name]) == _sign(case.realized_return)
                    else 0.0
                )
                grouped.setdefault(f"{name}:{key}", []).append((confidences[name], hit))

        maps: dict[str, ConfidenceMap] = {}
        for group_key, points in sorted(grouped.items()):
            if len(points) < self.min_cases_confidence:
                continue
            points_sorted = sorted(points)
            xs, ys = isotonic_regression(
                [conf for conf, _ in points_sorted],
                [hit for _, hit in points_sorted],
            )
            maps[group_key] = ConfidenceMap(x=xs, y=ys)
        return maps

    # -- weight learning ----------------------------------------------------

    def _mean_directional_return(
        self,
        cases: list[LabeledFusionCase],
        weights_bp: dict[str, int],
    ) -> float:
        returns: list[float] = []
        for case in cases:
            available = case.inputs.available()
            scores = signed_scores(case.inputs)
            total_bp = sum(weights_bp[name] for name in available)
            if total_bp == 0:
                continue
            net = round(sum(scores[name] * weights_bp[name] for name in available) / total_bp, 12)
            if abs(net) < self.flat_threshold:
                net = 0.0
            returns.append(_sign(net) * case.realized_return)
        return sum(returns) / len(returns) if returns else 0.0

    def _maybe_zero_llm(
        self,
        cases: list[LabeledFusionCase],
        learned: ComponentWeights,
        label: str,
        notes: list[str],
    ) -> tuple[ComponentWeights, bool]:
        """Zero the LLM weight for one case set when the LLM adds no measurable
        value: the learned weights must beat the best LLM-free weights by at
        least ``min_improvement`` (INV-16)."""
        if learned.llm_bp == 0:
            notes.append(f"{label}: learned weights already give the LLM zero weight")
            return learned, False
        learned_return = self._mean_directional_return(cases, learned.as_dict())
        without_llm = self._best_weights(cases, fixed={"llm": 0})
        without_return = self._mean_directional_return(cases, without_llm.as_dict())
        if learned_return <= without_return + self.min_improvement:
            notes.append(
                f"{label}: LLM weight zeroed — learned mean directional return "
                f"{learned_return:.6f} does not exceed best LLM-free "
                f"{without_return:.6f} by min_improvement {self.min_improvement} (INV-16)"
            )
            return without_llm, False
        notes.append(
            f"{label}: LLM keeps {learned.llm_bp} bp — mean directional return "
            f"{learned_return:.6f} > LLM-free {without_return:.6f} + {self.min_improvement}"
        )
        return learned, True

    def _best_weights(
        self,
        cases: list[LabeledFusionCase],
        *,
        fixed: dict[str, int] | None = None,
    ) -> ComponentWeights:
        """Grid search over basis-point compositions maximizing mean directional
        return. Ties break toward quant, then llm, then regime weight."""
        units = 10000 // self.weight_step_bp
        fixed = fixed or {}
        free = [name for name in COMPONENT_NAMES if name not in fixed]
        grid = _weight_grid(units, len(free))
        best: ComponentWeights | None = None
        best_key: tuple[float, int, int, int, int] = (-1e18, -1, -1, -1, -1)
        for units_combo in grid:
            weights_bp = dict(fixed)
            for name, units_value in zip(free, units_combo, strict=True):
                weights_bp[name] = units_value * self.weight_step_bp
            objective = self._mean_directional_return(cases, weights_bp)
            candidate = ComponentWeights.from_dict(weights_bp)
            key = (
                objective,
                candidate.quant_bp,
                candidate.llm_bp,
                candidate.regime_bp,
                candidate.memory_bp,
            )
            if key > best_key:
                best_key = key
                best = candidate
        assert best is not None
        return best

    # -- calibration entry point --------------------------------------------

    def calibrate(
        self,
        cases: list[LabeledFusionCase],
        *,
        name: str,
        trained_at: datetime,
    ) -> CalibrationArtifact:
        if not cases:
            raise CalibrationInsufficientDataError("cannot calibrate on an empty case set")

        notes: list[str] = []

        # 1. confidence calibration per producer
        confidence_maps = self._confidence_maps(cases)

        # 2. default weights on all cases
        default_weights = self._best_weights(cases)

        # 3. regime-specific weights (only for regimes with enough cases)
        regime_weights: dict[str, ComponentWeights] = {}
        by_regime: dict[str, list[LabeledFusionCase]] = {}
        for case in cases:
            if case.inputs.regime is not None:
                by_regime.setdefault(case.inputs.regime.regime, []).append(case)
        for regime, regime_cases in sorted(by_regime.items()):
            if len(regime_cases) >= self.min_cases_per_regime:
                regime_weights[regime] = self._best_weights(regime_cases)
                notes.append(
                    f"regime {regime!r}: {len(regime_cases)} cases, "
                    f"weights={regime_weights[regime].as_dict()}"
                )
            else:
                notes.append(
                    f"regime {regime!r}: only {len(regime_cases)} cases "
                    f"(< {self.min_cases_per_regime}); falls back to default weights"
                )

        # 4. LLM value test, applied per weight set: quant_plus_llm must beat
        # the best LLM-free weights measurably, else the LLM gets zero weight.
        llm_kept_anywhere = False
        default_weights, default_kept = self._maybe_zero_llm(
            cases, default_weights, "default", notes
        )
        llm_kept_anywhere = llm_kept_anywhere or default_kept
        for regime in list(regime_weights):
            regime_weights[regime], kept = self._maybe_zero_llm(
                by_regime[regime], regime_weights[regime], f"regime {regime!r}", notes
            )
            llm_kept_anywhere = llm_kept_anywhere or kept
        llm_added_value = llm_kept_anywhere

        # 5. assemble the deterministic configuration
        hyperparameters: dict[str, Any] = {
            "name": name,
            "weight_step_bp": self.weight_step_bp,
            "min_cases_per_regime": self.min_cases_per_regime,
            "min_cases_confidence": self.min_cases_confidence,
            "min_improvement": self.min_improvement,
            "flat_threshold": self.flat_threshold,
            "disagreement_policy": self.disagreement_policy.value,
            "missing_policy": self.missing_policy.value,
            "engine_version": FUSION_ENGINE_VERSION,
            "cases_hash": compute_cases_hash(cases),
        }
        calibration_version = hashlib.sha256(
            canonical_dumps(hyperparameters).encode("utf-8")
        ).hexdigest()[:12]

        config = FusionConfig(
            name=name,
            version=calibration_version,
            default_weights=default_weights,
            regime_weights=regime_weights,
            confidence_calibration=confidence_maps,
            disagreement_policy=self.disagreement_policy,
            missing_policy=self.missing_policy,
            flat_threshold=self.flat_threshold,
            compared_against=list(DEFAULT_BASELINES),
            notes=(
                f"calibrated on {len(cases)} cases; llm_added_value={llm_added_value}; "
                f"llm_weight_bp={default_weights.llm_bp}"
            ),
        )

        # 6. baseline comparison on the training set
        train_metrics = evaluate_cases(
            cases,
            config=config,
            evaluated_at=trained_at,
        ).metrics

        return CalibrationArtifact(
            artifact_id=uuid5(_CALIBRATION_NAMESPACE, calibration_version),
            calibration_version=calibration_version,
            engine_version=FUSION_ENGINE_VERSION,
            config=config,
            trained_at=trained_at,
            data_scope=self._data_scope(cases),
            train_metrics=train_metrics,
            llm_added_value=llm_added_value,
            llm_weight_bp=default_weights.llm_bp,
            selection_notes=notes,
        )

    @staticmethod
    def _data_scope(cases: list[LabeledFusionCase]) -> DataScope:
        instruments: list[str] = []
        quant_models: list[str] = []
        llm_models: list[str] = []
        regime_labels: list[str] = []
        as_ofs: list[datetime] = []
        for case in cases:
            if case.inputs.quant is not None:
                instruments.append(case.inputs.quant.instrument_id)
                quant_models.append(case.inputs.quant.model_id)
            elif case.inputs.llm is not None:
                instruments.append(case.inputs.llm.instrument_id)
            if case.inputs.llm is not None:
                llm_models.append(case.inputs.llm.model_name)
            if case.inputs.regime is not None:
                regime_labels.append(case.inputs.regime.regime)
            as_ofs.append(case.as_of)
        return DataScope(
            n_cases=len(cases),
            instrument_ids=sorted(set(instruments)),
            quant_models=sorted(set(quant_models)),
            llm_models=sorted(set(llm_models)),
            regime_labels=sorted(set(regime_labels)),
            as_of_from=min(as_ofs),
            as_of_to=max(as_ofs),
        )


def calibrate(
    cases: list[LabeledFusionCase],
    *,
    name: str,
    trained_at: datetime,
    **kwargs: Any,
) -> CalibrationArtifact:
    """Convenience wrapper around :class:`Calibrator`."""
    return Calibrator(**kwargs).calibrate(cases, name=name, trained_at=trained_at)
