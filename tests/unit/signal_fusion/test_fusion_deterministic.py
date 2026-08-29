"""Deterministic configuration: identical inputs produce identical outputs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from core.schemas.fusion import FusionInputs
from engines.signal_fusion.config import ComponentWeights, FusionConfig
from engines.signal_fusion.fusion import compute_fusion_hash, fuse_signals
from pydantic import ValidationError

from factories import make_llm_signal, make_memory_context, make_quant_signal, make_regime_context

T0 = datetime(2026, 1, 5, 10, 0, 0, tzinfo=UTC)


def make_config() -> FusionConfig:
    return FusionConfig(
        name="det-config",
        version="cal-det-1",
        default_weights=ComponentWeights(quant_bp=5000, llm_bp=3000, regime_bp=1500, memory_bp=500),
        regime_weights={
            "vol_crisis": ComponentWeights(
                quant_bp=2000, llm_bp=1000, regime_bp=6000, memory_bp=1000
            )
        },
    )


def test_uncalibrated_config_is_rejected() -> None:
    """INV-16: arbitrary (uncalibrated) weights must never be executable."""
    with pytest.raises(ValidationError):
        FusionConfig(
            name="det-config",
            default_weights=ComponentWeights(
                quant_bp=2500, llm_bp=2500, regime_bp=2500, memory_bp=2500
            ),
        )


def make_inputs() -> FusionInputs:
    return FusionInputs(
        quant=make_quant_signal(T0),
        llm=make_llm_signal(T0),
        regime=make_regime_context(T0),
        memory=make_memory_context(T0),
    )


class TestDeterminism:
    def test_same_inputs_produce_identical_signals(self) -> None:
        inputs = make_inputs()
        first = fuse_signals(inputs=inputs, config=make_config(), produced_at=T0)
        second = fuse_signals(inputs=inputs, config=make_config(), produced_at=T0)
        assert first is not None and second is not None
        assert first.signal_id == second.signal_id
        assert first.model_dump_json() == second.model_dump_json()

    def test_signal_id_is_stable_across_produced_at(self) -> None:
        later = T0 + timedelta(minutes=5)
        inputs = make_inputs()
        first = fuse_signals(inputs=inputs, config=make_config(), produced_at=T0)
        second = fuse_signals(inputs=inputs, config=make_config(), produced_at=later)
        assert first is not None and second is not None
        assert first.signal_id == second.signal_id

    def test_hash_changes_with_weights(self) -> None:
        config_a = make_config()
        config_b = config_a.model_copy(
            update={
                "default_weights": ComponentWeights(
                    quant_bp=6000, llm_bp=2000, regime_bp=1500, memory_bp=500
                )
            }
        )
        assert compute_fusion_hash(inputs=make_inputs(), config=config_a) != compute_fusion_hash(
            inputs=make_inputs(), config=config_b
        )

    def test_hash_changes_with_inputs(self) -> None:
        config = make_config()
        hash_a = compute_fusion_hash(inputs=make_inputs(), config=config)
        changed = FusionInputs(
            quant=make_quant_signal(T0, strength=0.81),
            llm=make_llm_signal(T0),
            regime=make_regime_context(T0),
            memory=make_memory_context(T0),
        )
        assert hash_a != compute_fusion_hash(inputs=changed, config=config)

    def test_regime_specific_weights_applied_deterministically(self) -> None:
        inputs = FusionInputs(
            quant=make_quant_signal(T0, strength=0.8),
            llm=make_llm_signal(T0, strength=0.6),
            regime=make_regime_context(T0, regime="vol_crisis", score=0.4),
            memory=make_memory_context(T0, score=0.5),
        )
        first = fuse_signals(inputs=inputs, config=make_config(), produced_at=T0)
        second = fuse_signals(inputs=inputs, config=make_config(), produced_at=T0)
        assert first is not None and second is not None
        assert first.to_json() == second.to_json()
        # vol_crisis weights: 2000/1000/6000/1000 over 10000 → no renormalization.
        assert first.fused_strength == pytest.approx(
            0.2 * 0.8 + 0.1 * 0.6 + 0.6 * 0.4 + 0.1 * 0.5, abs=1e-9
        )

    def test_config_is_immutable(self) -> None:
        config = make_config()
        with pytest.raises(ValidationError):
            config.default_weights = ComponentWeights(  # type: ignore[misc]
                quant_bp=0, llm_bp=0, regime_bp=0, memory_bp=10000
            )

    def test_weights_are_exact_basis_points(self) -> None:
        config = make_config()
        weights = config.default_weights
        assert (weights.quant_bp + weights.llm_bp + weights.regime_bp + weights.memory_bp) == 10000
        assert weights.as_dict() == {"quant": 5000, "llm": 3000, "regime": 1500, "memory": 500}
