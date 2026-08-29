"""Disagreement handling: conflicting quant vs LLM directions (INV-16)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from core.domain.enums import SignalDirection
from core.schemas.fusion import FusionInputs
from engines.signal_fusion.config import (
    ComponentWeights,
    ConfidenceMap,
    DisagreementPolicy,
    FusionConfig,
)
from engines.signal_fusion.fusion import fuse_signals

from factories import make_llm_signal, make_quant_signal

T0 = datetime(2026, 1, 5, 10, 0, 0, tzinfo=UTC)


def make_conflicting_inputs() -> FusionInputs:
    return FusionInputs(
        quant=make_quant_signal(T0, direction=SignalDirection.LONG, strength=0.8, confidence=0.9),
        llm=make_llm_signal(T0, direction=SignalDirection.SHORT, strength=0.6, confidence=0.5),
    )


def make_config(policy: DisagreementPolicy, **overrides: object) -> FusionConfig:
    base = {
        "name": "conflict-config",
        "version": "cal-conflict-1",
        "default_weights": ComponentWeights(quant_bp=5000, llm_bp=5000, regime_bp=0, memory_bp=0),
        "disagreement_policy": policy,
    }
    base.update(overrides)
    return FusionConfig(**base)  # type: ignore[arg-type]


class TestConflictingSignals:
    def test_neutralize_cancels_linearly_and_records(self) -> None:
        fused = fuse_signals(
            inputs=make_conflicting_inputs(),
            config=make_config(DisagreementPolicy.NEUTRALIZE),
            produced_at=T0,
        )
        assert fused is not None
        assert fused.direction is SignalDirection.LONG
        assert fused.fused_strength == pytest.approx(0.5 * 0.8 - 0.5 * 0.6, abs=1e-9)
        assert len(fused.disagreements) == 1
        record = fused.disagreements[0]
        assert record.policy_applied == "NEUTRALIZE"
        assert set(record.components) == {"quant", "llm"}

    def test_require_consensus_flattens(self) -> None:
        fused = fuse_signals(
            inputs=make_conflicting_inputs(),
            config=make_config(DisagreementPolicy.REQUIRE_CONSENSUS),
            produced_at=T0,
        )
        assert fused is not None
        assert fused.direction is SignalDirection.FLAT
        assert fused.fused_strength == 0.0
        assert all(component.score == 0.0 for component in fused.components)
        assert fused.disagreements[0].policy_applied == "REQUIRE_CONSENSUS"

    def test_trust_higher_confidence_picks_winner(self) -> None:
        fused = fuse_signals(
            inputs=make_conflicting_inputs(),
            config=make_config(DisagreementPolicy.TRUST_HIGHER_CONFIDENCE),
            produced_at=T0,
        )
        assert fused is not None
        # quant confidence 0.9 > llm confidence 0.5 → llm abstains, score 0.
        llm_component = next(c for c in fused.components if c.name == "llm")
        assert llm_component.score == 0.0
        assert fused.direction is SignalDirection.LONG
        assert fused.disagreements[0].policy_applied == "TRUST_HIGHER_CONFIDENCE"
        assert fused.disagreements[0].detail == "winner=quant"

    def test_trust_higher_confidence_respects_calibrated_confidence(self) -> None:
        # Calibration inverts the winner: raw quant 0.9 → calibrated 0.2,
        # raw llm 0.5 → calibrated 0.8.
        config = make_config(
            DisagreementPolicy.TRUST_HIGHER_CONFIDENCE,
            confidence_calibration={
                "quant:model-01": ConfidenceMap(x=[0.9], y=[0.2]),
                "llm:gpt-4o": ConfidenceMap(x=[0.5], y=[0.8]),
            },
        )
        fused = fuse_signals(inputs=make_conflicting_inputs(), config=config, produced_at=T0)
        assert fused is not None
        quant_component = next(c for c in fused.components if c.name == "quant")
        assert quant_component.score == 0.0
        assert fused.direction is SignalDirection.SHORT
        assert fused.disagreements[0].detail == "winner=llm"

    def test_no_disagreement_record_when_aligned(self) -> None:
        inputs = FusionInputs(
            quant=make_quant_signal(T0, direction=SignalDirection.LONG),
            llm=make_llm_signal(T0, direction=SignalDirection.LONG),
        )
        fused = fuse_signals(
            inputs=inputs,
            config=make_config(DisagreementPolicy.REQUIRE_CONSENSUS),
            produced_at=T0,
        )
        assert fused is not None
        assert fused.disagreements == []
        assert fused.direction is SignalDirection.LONG

    def test_flat_components_never_conflict(self) -> None:
        inputs = FusionInputs(
            quant=make_quant_signal(T0, direction=SignalDirection.LONG),
            llm=make_llm_signal(T0, direction=SignalDirection.FLAT),
        )
        fused = fuse_signals(
            inputs=inputs,
            config=make_config(DisagreementPolicy.REQUIRE_CONSENSUS),
            produced_at=T0,
        )
        assert fused is not None
        assert fused.disagreements == []
        assert fused.direction is SignalDirection.LONG
