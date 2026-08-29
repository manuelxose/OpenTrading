"""Signal Fusion Engine core tests: weighted math, thresholds, errors."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from core.domain.enums import SignalDirection
from core.schemas.fusion import FusionInputs
from engines.signal_fusion.config import ComponentWeights, FusionConfig
from engines.signal_fusion.errors import FusionError
from engines.signal_fusion.fusion import fuse_signals

from factories import make_llm_signal, make_memory_context, make_quant_signal, make_regime_context

T0 = datetime(2026, 1, 5, 10, 0, 0, tzinfo=UTC)


def make_config(**overrides: object) -> FusionConfig:
    base = {
        "name": "test-config",
        "version": "cal-test-1",
        "default_weights": ComponentWeights(
            quant_bp=5000, llm_bp=3000, regime_bp=1500, memory_bp=500
        ),
    }
    base.update(overrides)
    return FusionConfig(**base)  # type: ignore[arg-type]


class TestWeightedMath:
    def test_fused_strength_is_weighted_sum(self) -> None:
        inputs = FusionInputs(
            quant=make_quant_signal(T0, strength=0.8),
            llm=make_llm_signal(T0, strength=0.6),
            regime=make_regime_context(T0, score=0.5),
            memory=make_memory_context(T0, score=0.5),
        )
        fused = fuse_signals(inputs=inputs, config=make_config(), produced_at=T0)
        assert fused is not None
        expected = 0.5 * 0.8 + 0.3 * 0.6 + 0.15 * 0.5 + 0.05 * 0.5
        assert fused.fused_strength == pytest.approx(expected, abs=1e-9)
        assert fused.direction is SignalDirection.LONG
        assert fused.missing_inputs == []

    def test_short_components_produce_short_signal(self) -> None:
        inputs = FusionInputs(
            quant=make_quant_signal(T0, direction=SignalDirection.SHORT, strength=0.8),
            llm=make_llm_signal(T0, direction=SignalDirection.SHORT, strength=0.6),
        )
        fused = fuse_signals(inputs=inputs, config=make_config(), produced_at=T0)
        assert fused is not None
        assert fused.direction is SignalDirection.SHORT
        # weights renormalized over the two present inputs: 5000/8000 and 3000/8000.
        assert fused.fused_strength == pytest.approx(0.625 * 0.8 + 0.375 * 0.6, abs=1e-9)

    def test_flat_input_abstains_but_keeps_weight(self) -> None:
        inputs = FusionInputs(
            quant=make_quant_signal(T0, direction=SignalDirection.FLAT, strength=0.8),
            llm=make_llm_signal(T0, strength=0.6),
        )
        fused = fuse_signals(inputs=inputs, config=make_config(), produced_at=T0)
        assert fused is not None
        # quant abstains (score 0) but still consumes its renormalized share.
        assert fused.fused_strength == pytest.approx(0.375 * 0.6, abs=1e-9)

    def test_flat_threshold_forces_flat(self) -> None:
        inputs = FusionInputs(
            quant=make_quant_signal(T0, strength=0.02),
            llm=make_llm_signal(T0, direction=SignalDirection.SHORT, strength=0.01),
        )
        config = make_config(flat_threshold=0.01)
        fused = fuse_signals(inputs=inputs, config=config, produced_at=T0)
        assert fused is not None
        assert fused.direction is SignalDirection.FLAT
        assert fused.fused_strength == 0.0

    def test_confidence_is_weighted_calibrated_mean(self) -> None:
        inputs = FusionInputs(
            quant=make_quant_signal(T0, confidence=1.0),
            llm=make_llm_signal(T0, confidence=0.0),
        )
        fused = fuse_signals(inputs=inputs, config=make_config(), produced_at=T0)
        assert fused is not None
        assert fused.confidence == pytest.approx(0.625 * 1.0 + 0.375 * 0.0, abs=1e-9)


class TestEngineErrors:
    def test_no_inputs_returns_none(self) -> None:
        fused = fuse_signals(inputs=FusionInputs(), config=make_config(), produced_at=T0)
        assert fused is None

    def test_future_input_rejected(self) -> None:
        future = datetime(2026, 1, 5, 11, 0, 0, tzinfo=UTC)
        inputs = FusionInputs(quant=make_quant_signal(future))
        with pytest.raises(FusionError, match="future"):
            fuse_signals(inputs=inputs, config=make_config(), produced_at=T0)

    def test_zero_weight_coverage_falls_back_to_equal_weights(self) -> None:
        inputs = FusionInputs(llm=make_llm_signal(T0, strength=0.6))
        config = make_config(
            default_weights=ComponentWeights(quant_bp=10000, llm_bp=0, regime_bp=0, memory_bp=0)
        )
        fused = fuse_signals(inputs=inputs, config=config, produced_at=T0)
        assert fused is not None
        # llm-only present: equal-weight fallback gives it the full share.
        assert fused.fused_strength == pytest.approx(0.6, abs=1e-9)

    def test_instrument_mismatch_rejected(self) -> None:
        inputs = FusionInputs(
            quant=make_quant_signal(T0, instrument_id="EURUSD"),
            llm=make_llm_signal(T0, instrument_id="GBPUSD"),
        )
        with pytest.raises(FusionError, match="instrument"):
            fuse_signals(inputs=inputs, config=make_config(), produced_at=T0)

    def test_component_weights_must_sum_exactly(self) -> None:
        with pytest.raises(Exception, match="10000"):
            ComponentWeights(quant_bp=5000, llm_bp=3000, regime_bp=1500, memory_bp=0)
