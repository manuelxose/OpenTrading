"""Extreme confidence / score values: boundaries are accepted, garbage rejected."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from core.domain.enums import SignalDirection
from core.schemas.fusion import FusionInputs, MemoryContext, RegimeContext
from engines.signal_fusion.config import ComponentWeights, FusionConfig
from engines.signal_fusion.fusion import fuse_signals
from pydantic import ValidationError

from factories import make_llm_signal, make_quant_signal

T0 = datetime(2026, 1, 5, 10, 0, 0, tzinfo=UTC)


def make_config(**overrides: object) -> FusionConfig:
    base = {
        "name": "extreme-config",
        "version": "cal-extreme-1",
        "default_weights": ComponentWeights(quant_bp=5000, llm_bp=5000, regime_bp=0, memory_bp=0),
    }
    base.update(overrides)
    return FusionConfig(**base)  # type: ignore[arg-type]


class TestExtremeConfidence:
    def test_confidence_zero_and_one_fuse_sanely(self) -> None:
        inputs = FusionInputs(
            quant=make_quant_signal(T0, confidence=0.0, strength=0.8),
            llm=make_llm_signal(T0, confidence=1.0, strength=0.6),
        )
        fused = fuse_signals(inputs=inputs, config=make_config(), produced_at=T0)
        assert fused is not None
        assert 0.0 <= fused.confidence <= 1.0
        assert fused.fused_strength == pytest.approx(0.7, abs=1e-9)

    def test_strength_zero_and_one_are_valid(self) -> None:
        inputs = FusionInputs(
            quant=make_quant_signal(T0, strength=0.0),
            llm=make_llm_signal(T0, strength=1.0),
        )
        fused = fuse_signals(inputs=inputs, config=make_config(), produced_at=T0)
        assert fused is not None
        assert fused.fused_strength == pytest.approx(0.5, abs=1e-9)

    def test_confidence_above_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_quant_signal(T0, confidence=1.5)

    def test_confidence_below_zero_rejected(self) -> None:
        with pytest.raises(ValidationError):
            make_llm_signal(T0, confidence=-0.1)

    def test_nan_score_rejected_on_regime_context(self) -> None:
        with pytest.raises(ValidationError):
            RegimeContext(
                regime="trend_up",
                direction=SignalDirection.LONG,
                score=float("nan"),
                confidence=0.5,
                classifier_version="regime-v1",
                source="engines.regime.v1",
                as_of=T0,
            )

    def test_nan_confidence_rejected_on_memory_context(self) -> None:
        with pytest.raises(ValidationError):
            MemoryContext(
                direction=SignalDirection.LONG,
                score=0.5,
                confidence=float("nan"),
                memory_version="mem-v1",
                source="engines.memory.v1",
                as_of=T0,
            )
