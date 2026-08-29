"""Research evaluation for Signal Fusion (INV-16).

Evaluates labeled history under the four mandatory configurations —
quant_only, llm_only, quant_plus_llm, and the simple baseline — and reports
deterministic, comparable metrics. The calibration stage reuses the same
scorer, so the numbers that select weights are exactly the numbers reported.

The "simple baseline" is defined as an equal-weight average of whichever
inputs are present, with raw (uncalibrated) confidences — no learned weights,
no confidence calibration. ``quant_plus_llm`` uses the calibrated,
regime-aware weights of the configuration under evaluation.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any
from uuid import UUID, uuid5

from core.schemas.base import BaseContractModel, UtcDateTime
from core.schemas.fusion import FusionInputs
from pydantic import Field

from engines.signal_fusion.config import (
    COMPONENT_NAMES,
    DEFAULT_BASELINES,
    FusionConfig,
)
from engines.signal_fusion.errors import CalibrationInsufficientDataError
from engines.signal_fusion.fusion import (
    canonical_dumps,
    inputs_canonical,
    producer_keys,
    raw_confidences,
    signed_scores,
)

__all__ = [
    "CONFIG_COMPARISON_ORDER",
    "ConfigMetrics",
    "EvaluationReport",
    "LabeledFusionCase",
    "compute_cases_hash",
    "evaluate_cases",
]

#: Deterministic tie-break order for picking a winner (conservative first).
CONFIG_COMPARISON_ORDER: tuple[str, ...] = DEFAULT_BASELINES

_EVAL_NAMESPACE = UUID("7b2e6d4a-9c1e-4f2b-8a5d-3e6f0c1d9a2b")


class LabeledFusionCase(BaseContractModel):
    """One labeled training/evaluation case: fusion inputs + realized outcome.

    ``realized_return`` is the signed forward return over the fusion horizon
    (quote-currency terms). The realized direction is its sign; zero means the
    market went nowhere.
    """

    inputs: FusionInputs
    realized_return: float = Field(allow_inf_nan=False)
    as_of: UtcDateTime


class ConfigMetrics(BaseContractModel):
    """Performance of one configuration on one case set."""

    config_name: str = Field(min_length=1)
    component_weights: dict[str, int]
    n_cases: int = Field(ge=0)
    directional_accuracy: float | None = None
    mean_return: float | None = None
    std_return: float | None = None
    information_ratio: float | None = None
    ece: float | None = None
    n_flat: int = Field(default=0, ge=0)


class EvaluationReport(BaseContractModel):
    """Full comparison of the mandatory configurations on one case set."""

    report_id: UUID
    config_name: str = Field(min_length=1)
    config_version: str = Field(min_length=1)
    evaluated_at: UtcDateTime
    cases_hash: str = Field(min_length=1)
    n_cases: int = Field(ge=0)
    metrics: list[ConfigMetrics]
    winner: str = Field(min_length=1)
    notes: list[str] = Field(default_factory=list)


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _baseline_weights_bp(available: list[str]) -> dict[str, int]:
    """Equal-weight split in basis points over the present inputs (remainder to
    the first components, in canonical order — fully deterministic)."""
    if not available:
        raise CalibrationInsufficientDataError("no available inputs to weight")
    share, remainder = divmod(10000, len(available))
    weights = dict.fromkeys(available, share)
    for name in COMPONENT_NAMES:
        if remainder <= 0:
            break
        if name in weights:
            weights[name] += 1
            remainder -= 1
    return weights


def _case_net(
    *,
    scores: dict[str, float],
    available: list[str],
    weights_bp: dict[str, int],
    flat_threshold: float,
) -> float:
    total_bp = sum(weights_bp[name] for name in available)
    if total_bp == 0:
        return 0.0
    net = sum(scores[name] * weights_bp[name] for name in available) / total_bp
    net = round(net, 12)
    if abs(net) < flat_threshold:
        return 0.0
    return net


def compute_cases_hash(cases: list[LabeledFusionCase]) -> str:
    """Deterministic hash over labeled cases (inputs + realized outcomes)."""
    canonical: list[dict[str, Any]] = [
        {
            "inputs": inputs_canonical(case.inputs),
            "realized_return": round(case.realized_return, 12),
            "as_of": case.as_of.isoformat(),
        }
        for case in cases
    ]
    return hashlib.sha256(canonical_dumps(canonical).encode("utf-8")).hexdigest()


def compute_metrics(
    cases: list[LabeledFusionCase],
    *,
    config_name: str,
    config: FusionConfig,
    weights_bp: dict[str, int] | None,
    calibrate_confidence: bool,
    regime_aware: bool = False,
    n_confidence_bins: int = 10,
) -> ConfigMetrics:
    """Score one configuration over labeled cases.

    ``weights_bp=None`` selects either the dynamic equal-weight baseline or,
    with ``regime_aware=True``, the calibrated regime-specific weights per case
    (production behavior). ``calibrate_confidence=False`` uses raw confidences
    (baseline behavior).
    """
    hits = 0
    flats = 0
    returns: list[float] = []
    confidence_bins: list[list[tuple[float, int]]] = [[] for _ in range(n_confidence_bins)]

    for case in cases:
        available = case.inputs.available()
        scores = signed_scores(case.inputs)
        confidences = raw_confidences(case.inputs)
        keys = producer_keys(case.inputs)

        if weights_bp is not None:
            effective_weights = weights_bp
        elif regime_aware:
            regime = case.inputs.regime.regime if case.inputs.regime is not None else None
            effective_weights = config.weights_for_regime(regime).as_dict()
        else:
            effective_weights = _baseline_weights_bp(available)
        net = _case_net(
            scores=scores,
            available=available,
            weights_bp=effective_weights,
            flat_threshold=config.flat_threshold,
        )
        if net == 0.0:
            flats += 1
        elif _sign(net) == _sign(case.realized_return):
            hits += 1
        returns.append(_sign(net) * case.realized_return)

        total_bp = sum(effective_weights[name] for name in available)
        pred_confidence = (
            sum(
                (
                    config.calibrated_confidence(name, keys[name], confidences[name])
                    if calibrate_confidence
                    else confidences[name]
                )
                * effective_weights[name]
                for name in available
            )
            / total_bp
        )
        bin_index = min(int(pred_confidence * n_confidence_bins), n_confidence_bins - 1)
        hit = 1 if (_sign(net) == _sign(case.realized_return) and net != 0) else 0
        confidence_bins[bin_index].append((pred_confidence, hit))

    n = len(cases)
    mean_return = sum(returns) / n
    variance = sum((r - mean_return) ** 2 for r in returns) / n
    std_return = variance**0.5
    ece = (
        sum(
            (
                sum(conf for conf, _ in bin_cases) / len(bin_cases)
                - sum(hit for _, hit in bin_cases) / len(bin_cases)
            )
            ** 2
            * len(bin_cases)
            for bin_cases in confidence_bins
            if bin_cases
        )
        / n
    )
    return ConfigMetrics(
        config_name=config_name,
        component_weights=dict(effective_weights),
        n_cases=n,
        directional_accuracy=hits / n,
        mean_return=mean_return,
        std_return=std_return,
        information_ratio=(mean_return / std_return) if std_return > 0 else 0.0,
        ece=ece,
        n_flat=flats,
    )


def evaluate_cases(
    cases: list[LabeledFusionCase],
    *,
    config: FusionConfig,
    evaluated_at: datetime,
    regime_aware: bool = False,
) -> EvaluationReport:
    """Compare quant_only / llm_only / quant_plus_llm / baseline on ``cases``.

    Deterministic winner selection: highest mean return, ties broken by
    directional accuracy, then by the conservative comparison order.
    With ``regime_aware=True`` the ``quant_plus_llm`` configuration uses the
    calibrated regime-specific weights per case (production behavior).
    """
    if not cases:
        raise CalibrationInsufficientDataError("cannot evaluate an empty case set")

    weights_by_config: dict[str, dict[str, int]] = {
        "quant_only": {"quant": 10000, "llm": 0, "regime": 0, "memory": 0},
        "llm_only": {"quant": 0, "llm": 10000, "regime": 0, "memory": 0},
        "quant_plus_llm": config.default_weights.as_dict(),
    }
    metrics = [
        compute_metrics(
            cases,
            config_name="quant_only",
            config=config,
            weights_bp=weights_by_config["quant_only"],
            calibrate_confidence=True,
        ),
        compute_metrics(
            cases,
            config_name="llm_only",
            config=config,
            weights_bp=weights_by_config["llm_only"],
            calibrate_confidence=True,
        ),
        compute_metrics(
            cases,
            config_name="quant_plus_llm",
            config=config,
            weights_bp=weights_by_config["quant_plus_llm"] if not regime_aware else None,
            calibrate_confidence=True,
            regime_aware=regime_aware,
        ),
        compute_metrics(
            cases,
            config_name="baseline",
            config=config,
            weights_bp=None,
            calibrate_confidence=False,
        ),
    ]

    def rank(metric: ConfigMetrics) -> tuple[float, float, int]:
        return (
            metric.mean_return if metric.mean_return is not None else -1.0,
            metric.directional_accuracy if metric.directional_accuracy is not None else -1.0,
            -CONFIG_COMPARISON_ORDER.index(metric.config_name),
        )

    winner = max(metrics, key=rank).config_name
    return EvaluationReport(
        report_id=uuid5(_EVAL_NAMESPACE, compute_cases_hash(cases)),
        config_name=config.name,
        config_version=config.version,
        evaluated_at=evaluated_at,
        cases_hash=compute_cases_hash(cases),
        n_cases=len(cases),
        metrics=metrics,
        winner=winner,
    )
