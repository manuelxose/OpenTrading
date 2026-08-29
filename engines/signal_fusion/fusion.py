"""Deterministic Signal Fusion Engine (architecture §16, INV-16).

Pure function of its inputs, like the Risk Engine: no state, no IO, no wall
clock, no LLM call. Fuses ``QuantSignal``, ``LLMSignal``, ``RegimeContext`` and
``MemoryContext`` into ``FusedSignal`` using *calibrated* weights — never
arbitrary ones.

Semantics (kept deliberately simple and auditable):

- each present input contributes a signed score: ``+strength`` (LONG),
  ``-strength`` (SHORT), ``0`` (FLAT/abstain);
- the fused direction is the sign of the weighted sum; ``fused_strength`` is its
  absolute value; a net below ``flat_threshold`` is forced to FLAT;
- confidence is the weight-averaged, per-producer calibrated confidence;
- weights are renormalized over the present inputs (missing-signal policy);
- disagreements are recorded on the ``FusedSignal`` and resolved per the
  configured :class:`DisagreementPolicy`.

``FusedSignal`` is a decision input, never an order (INV-1): it stays separate
from ``TradeProposal`` — nothing here imports trading contracts.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid5

from core.clock.clocks import Clock
from core.domain.enums import SignalDirection
from core.schemas.base import Provenance, ensure_utc
from core.schemas.fusion import FusionInputs
from core.schemas.signals import DisagreementRecord, FusedSignal, SignalComponent

from engines.signal_fusion.config import (
    COMPONENT_NAMES,
    ComponentWeights,
    DisagreementPolicy,
    FusionConfig,
)
from engines.signal_fusion.errors import FusionConfigurationError, FusionError

__all__ = [
    "FUSION_ENGINE_VERSION",
    "FusionEngine",
    "available_components",
    "canonical_dumps",
    "compute_fusion_hash",
    "fuse_signals",
    "inputs_canonical",
    "producer_keys",
    "signed_scores",
]

FUSION_ENGINE_VERSION = "1.0.0"
_PRODUCER = "engines.signal_fusion"

#: Fixed namespace for deterministic signal ids (UUIDv5 over the inputs hash).
_FUSION_NAMESPACE = UUID("5f1a2b3c-4d5e-4f6a-8b7c-9d0e1f2a3b4c")

#: Rounding used for every fused float so results are bit-identical across runs.
_FLOAT_PRECISION = 12

_DIRECTION_SIGN = {
    SignalDirection.LONG: 1.0,
    SignalDirection.SHORT: -1.0,
    SignalDirection.FLAT: 0.0,
}


def available_components(inputs: FusionInputs) -> list[str]:
    """Names of the fusion inputs that are present, in canonical order."""
    return inputs.available()


def signed_scores(inputs: FusionInputs) -> dict[str, float]:
    """Raw signed score per present component (no weights, no calibration)."""
    scores: dict[str, float] = {}
    if inputs.quant is not None:
        scores["quant"] = _DIRECTION_SIGN[inputs.quant.direction] * inputs.quant.strength
    if inputs.llm is not None:
        scores["llm"] = _DIRECTION_SIGN[inputs.llm.direction] * inputs.llm.strength
    if inputs.regime is not None:
        scores["regime"] = _DIRECTION_SIGN[inputs.regime.direction] * inputs.regime.score
    if inputs.memory is not None:
        scores["memory"] = _DIRECTION_SIGN[inputs.memory.direction] * inputs.memory.score
    return scores


def raw_confidences(inputs: FusionInputs) -> dict[str, float]:
    """Raw confidence per present component."""
    confidences: dict[str, float] = {}
    if inputs.quant is not None:
        confidences["quant"] = inputs.quant.confidence
    if inputs.llm is not None:
        confidences["llm"] = inputs.llm.confidence
    if inputs.regime is not None:
        confidences["regime"] = inputs.regime.confidence
    if inputs.memory is not None:
        confidences["memory"] = inputs.memory.confidence
    return confidences


def producer_keys(inputs: FusionInputs) -> dict[str, str]:
    """Calibration key per present component (model/classifier identity)."""
    keys: dict[str, str] = {}
    if inputs.quant is not None:
        keys["quant"] = inputs.quant.model_id
    if inputs.llm is not None:
        keys["llm"] = inputs.llm.model_name
    if inputs.regime is not None:
        keys["regime"] = inputs.regime.classifier_version
    if inputs.memory is not None:
        keys["memory"] = inputs.memory.memory_version
    return keys


def input_as_of(inputs: FusionInputs) -> dict[str, datetime]:
    """Point-in-time timestamp per present component."""
    as_of: dict[str, datetime] = {}
    if inputs.quant is not None:
        as_of["quant"] = inputs.quant.as_of
    if inputs.llm is not None:
        as_of["llm"] = inputs.llm.as_of
    if inputs.regime is not None:
        as_of["regime"] = inputs.regime.as_of
    if inputs.memory is not None:
        as_of["memory"] = inputs.memory.as_of
    return as_of


def renormalized_weights(weights: ComponentWeights, available: list[str]) -> dict[str, float]:
    """Calibrated basis-point weights renormalized over the present inputs.

    When the calibration assigns zero share to every present input (e.g. an
    llm-only calibration facing a missing LLM), degrade deterministically to
    equal weights over the present inputs — never to an error or an arbitrary
    production weight.
    """
    total_bp = sum(weights.bp_for(name) for name in available)
    if total_bp == 0:
        share, remainder = divmod(10000, len(available))
        fallback = dict.fromkeys(available, share)
        for name in COMPONENT_NAMES:
            if remainder <= 0:
                break
            if name in fallback:
                fallback[name] += 1
                remainder -= 1
        return {name: round(fallback[name] / 10000, _FLOAT_PRECISION) for name in available}
    return {name: round(weights.bp_for(name) / total_bp, _FLOAT_PRECISION) for name in available}


def resolve_disagreements(
    *,
    scores: dict[str, float],
    confidences: dict[str, float],
    policy: DisagreementPolicy,
) -> tuple[dict[str, float], list[DisagreementRecord]]:
    """Apply the disagreement policy; returns (adjusted scores, records).

    A conflict exists when two present components with non-zero scores vote in
    opposite directions. FLAT (zero) components never conflict.
    """
    directional = [name for name in COMPONENT_NAMES if name in scores and scores[name] != 0.0]
    long_voters = [name for name in directional if scores[name] > 0]
    short_voters = [name for name in directional if scores[name] < 0]
    if not (long_voters and short_voters):
        return dict(scores), []

    voters = long_voters + short_voters
    record = DisagreementRecord(
        components=voters,
        policy_applied=policy.value,
        detail=f"LONG={long_voters} SHORT={short_voters}",
    )
    if policy is DisagreementPolicy.NEUTRALIZE:
        return dict(scores), [record]

    if policy is DisagreementPolicy.REQUIRE_CONSENSUS:
        adjusted = {name: (0.0 if name in directional else score) for name, score in scores.items()}
        return adjusted, [record]

    if policy is DisagreementPolicy.TRUST_HIGHER_CONFIDENCE:
        winner = max(voters, key=lambda name: (confidences[name], -COMPONENT_NAMES.index(name)))
        adjusted = {
            name: (0.0 if name in voters and name != winner else score)
            for name, score in scores.items()
        }
        record = DisagreementRecord(
            components=voters,
            policy_applied=policy.value,
            detail=f"winner={winner}",
        )
        return adjusted, [record]

    raise FusionConfigurationError(f"unknown disagreement policy {policy!r}")


def _json_default(value: object) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return round(value, _FLOAT_PRECISION)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (frozenset, set)):
        return sorted(_json_default(item) for item in value)
    raise TypeError(f"cannot canonicalize {type(value).__name__}")


def canonical_dumps(obj: Any) -> str:
    """Deterministic JSON text (sorted keys, compact separators, fixed float
    precision, UUID/datetime/enum normalization)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=_json_default)


def inputs_canonical(inputs: FusionInputs) -> dict[str, Any]:
    """JSON-ready canonical view of the decision-relevant input fields."""
    canonical: dict[str, Any] = {}
    if inputs.quant is not None:
        q = inputs.quant
        canonical["quant"] = {
            "signal_id": str(q.signal_id),
            "direction": q.direction.value,
            "strength": round(q.strength, _FLOAT_PRECISION),
            "confidence": round(q.confidence, _FLOAT_PRECISION),
            "score": q.score,
            "model_id": q.model_id,
            "model_version": q.model_version,
            "as_of": q.as_of.isoformat(),
        }
    if inputs.llm is not None:
        llm_input = inputs.llm
        canonical["llm"] = {
            "signal_id": str(llm_input.signal_id),
            "direction": llm_input.direction.value,
            "strength": round(llm_input.strength, _FLOAT_PRECISION),
            "confidence": round(llm_input.confidence, _FLOAT_PRECISION),
            "model_name": llm_input.model_name,
            "provider": llm_input.provider,
            "prompt_version": llm_input.prompt_version,
            "as_of": llm_input.as_of.isoformat(),
        }
    if inputs.regime is not None:
        r = inputs.regime
        canonical["regime"] = {
            "regime": r.regime,
            "direction": r.direction.value,
            "score": round(r.score, _FLOAT_PRECISION),
            "confidence": round(r.confidence, _FLOAT_PRECISION),
            "classifier_version": r.classifier_version,
            "as_of": r.as_of.isoformat(),
        }
    if inputs.memory is not None:
        m = inputs.memory
        canonical["memory"] = {
            "direction": m.direction.value,
            "score": round(m.score, _FLOAT_PRECISION),
            "confidence": round(m.confidence, _FLOAT_PRECISION),
            "memory_version": m.memory_version,
            "as_of": m.as_of.isoformat(),
        }
    return canonical


def _config_canonical(config: FusionConfig) -> dict[str, Any]:
    return {
        "name": config.name,
        "version": config.version,
        "default_weights": config.default_weights.as_dict(),
        "regime_weights": {
            regime: weights.as_dict() for regime, weights in sorted(config.regime_weights.items())
        },
        "confidence_calibration": {
            key: {"x": cal.x, "y": cal.y}
            for key, cal in sorted(config.confidence_calibration.items())
        },
        "disagreement_policy": config.disagreement_policy.value,
        "missing_policy": config.missing_policy.value,
        "flat_threshold": config.flat_threshold,
        "compared_against": config.compared_against,
    }


def compute_fusion_hash(*, inputs: FusionInputs, config: FusionConfig) -> str:
    """SHA-256 over the canonical JSON of every decision-relevant input.

    Deterministic across runs and processes (sorted keys, compact separators,
    fixed float precision). Not included: provenance, produced_at, trace_id.
    """
    canonical: dict[str, Any] = {
        "engine_version": FUSION_ENGINE_VERSION,
        "config": _config_canonical(config),
        "inputs": inputs_canonical(inputs),
    }
    return hashlib.sha256(canonical_dumps(canonical).encode("utf-8")).hexdigest()


def _net_and_direction(scores: dict[str, float], weights: dict[str, float]) -> float:
    net = sum(scores[name] * weights[name] for name in weights)
    return round(net, _FLOAT_PRECISION)


def fuse_signals(
    *,
    inputs: FusionInputs,
    config: FusionConfig,
    produced_at: datetime,
    trace_id: UUID | None = None,
) -> FusedSignal | None:
    """Fuse one input bundle into a ``FusedSignal`` — or ``None`` when there is
    no signal (nothing to fuse, or the missing-signal policy forbids it).

    Deterministic: identical inputs + config + policies produce an identical
    ``FusedSignal`` (same signal_id, same JSON).
    """
    now = ensure_utc(produced_at)
    available = available_components(inputs)

    if not available:
        return None
    if config.missing_policy.value == "REQUIRE_QUANT" and "quant" not in available:
        return None

    for name in available:
        as_of = input_as_of(inputs)[name]
        if as_of > now:
            raise FusionError(
                f"input {name!r} as_of {as_of.isoformat()} is in the future relative "
                f"to evaluation time {now.isoformat()} (INV-3)"
            )

    scores = signed_scores(inputs)
    raw_conf = raw_confidences(inputs)
    keys = producer_keys(inputs)
    calibrated_conf = {
        name: config.calibrated_confidence(name, keys[name], raw_conf[name]) for name in available
    }

    scores, disagreements = resolve_disagreements(
        scores=scores,
        confidences=calibrated_conf,
        policy=config.disagreement_policy,
    )

    weights = renormalized_weights(
        config.weights_for_regime(inputs.regime.regime if inputs.regime is not None else None),
        available,
    )

    net = _net_and_direction(scores, weights)
    if abs(net) < config.flat_threshold:
        # Below threshold the fused signal has no conviction: every component
        # abstains so the FusedSignal contract (FLAT ⟺ zero net score) holds.
        scores = dict.fromkeys(available, 0.0)
        net = 0.0

    fused_strength = round(abs(net), _FLOAT_PRECISION)
    if net > 0:
        direction = SignalDirection.LONG
    elif net < 0:
        direction = SignalDirection.SHORT
    else:
        direction = SignalDirection.FLAT
    confidence = round(
        sum(calibrated_conf[name] * weights[name] for name in available), _FLOAT_PRECISION
    )
    confidence = min(1.0, max(0.0, confidence))

    components = [
        SignalComponent(
            name=name,
            score=round(scores[name], _FLOAT_PRECISION),
            weight=weights[name],
        )
        for name in available
    ]
    missing = [name for name in COMPONENT_NAMES if name not in available]
    as_of = max(input_as_of(inputs)[name] for name in available)

    signal_id = uuid5(_FUSION_NAMESPACE, compute_fusion_hash(inputs=inputs, config=config))
    provenance = Provenance(
        producer=_PRODUCER,
        produced_at=now,
        code_version=FUSION_ENGINE_VERSION,
        source_ids={
            "quant_signal_id": (
                str(inputs.quant.signal_id) if inputs.quant is not None else "absent"
            ),
            "llm_signal_id": (str(inputs.llm.signal_id) if inputs.llm is not None else "absent"),
        },
    )
    return FusedSignal(
        signal_id=signal_id,
        instrument_id=_instrument_of(inputs),
        direction=direction,
        fused_strength=fused_strength,
        confidence=confidence,
        components=components,
        calibration_version=config.version,
        calibration_notes=config.notes,
        compared_against=list(config.compared_against),
        missing_inputs=missing,
        disagreements=disagreements,
        as_of=as_of,
        produced_at=now,
        provenance=provenance,
        trace_id=trace_id,
    )


def _instrument_of(inputs: FusionInputs) -> str:
    instrument_ids = {
        name: str(component.instrument_id)
        for name, component in (("quant", inputs.quant), ("llm", inputs.llm))
        if component is not None
    }
    if not instrument_ids:
        raise FusionError("no fusion input carries an instrument_id")
    if len(set(instrument_ids.values())) > 1:
        raise FusionError(f"fusion inputs disagree on instrument: {sorted(instrument_ids.items())}")
    return next(iter(instrument_ids.values()))


class FusionEngine:
    """Convenience wrapper binding a configuration to a :class:`Clock`."""

    def __init__(self, config: FusionConfig, *, clock: Clock) -> None:
        self._config = config
        self._clock = clock

    def fuse(self, inputs: FusionInputs) -> FusedSignal | None:
        return fuse_signals(inputs=inputs, config=self._config, produced_at=self._clock.now())
