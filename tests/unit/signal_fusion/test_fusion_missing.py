"""Missing-signal handling: absent LLM / QuantSignal inputs (INV-16)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from core.schemas.fusion import FusionInputs
from engines.signal_fusion.config import (
    ComponentWeights,
    FusionConfig,
    MissingSignalPolicy,
)
from engines.signal_fusion.fusion import fuse_signals

from factories import make_llm_signal, make_memory_context, make_quant_signal, make_regime_context

T0 = datetime(2026, 1, 5, 10, 0, 0, tzinfo=UTC)


def make_config(**overrides: object) -> FusionConfig:
    base = {
        "name": "missing-config",
        "version": "cal-missing-1",
        "default_weights": ComponentWeights(
            quant_bp=5000, llm_bp=3000, regime_bp=1500, memory_bp=500
        ),
    }
    base.update(overrides)
    return FusionConfig(**base)  # type: ignore[arg-type]


class TestMissingLLM:
    def test_llm_missing_renormalizes_weights(self) -> None:
        inputs = FusionInputs(
            quant=make_quant_signal(T0, strength=0.8),
            regime=make_regime_context(T0, score=0.5),
            memory=make_memory_context(T0, score=0.5),
        )
        fused = fuse_signals(inputs=inputs, config=make_config(), produced_at=T0)
        assert fused is not None
        assert fused.missing_inputs == ["llm"]
        assert [c.name for c in fused.components] == ["quant", "regime", "memory"]
        # weights renormalized over 7000 bp: 5000/7000, 1500/7000, 500/7000.
        weights = {c.name: c.weight for c in fused.components}
        assert weights["quant"] == pytest.approx(5000 / 7000, abs=1e-9)
        assert weights["regime"] == pytest.approx(1500 / 7000, abs=1e-9)
        assert weights["memory"] == pytest.approx(500 / 7000, abs=1e-9)
        assert sum(weights.values()) == pytest.approx(1.0, abs=1e-9)

    def test_llm_only_configuration_fuses_quant_alone(self) -> None:
        config = make_config(
            default_weights=ComponentWeights(quant_bp=0, llm_bp=10000, regime_bp=0, memory_bp=0)
        )
        inputs = FusionInputs(quant=make_quant_signal(T0, strength=0.8))
        fused = fuse_signals(inputs=inputs, config=config, produced_at=T0)
        assert fused is not None
        assert fused.missing_inputs == ["llm", "regime", "memory"]
        assert fused.fused_strength == pytest.approx(0.8)


class TestMissingQuant:
    def test_missing_quant_renormalizes_by_default(self) -> None:
        inputs = FusionInputs(
            llm=make_llm_signal(T0, strength=0.6),
            regime=make_regime_context(T0, score=0.5),
        )
        fused = fuse_signals(inputs=inputs, config=make_config(), produced_at=T0)
        assert fused is not None
        assert fused.missing_inputs == ["quant", "memory"]
        assert fused.direction.value == "LONG"

    def test_require_quant_policy_returns_none(self) -> None:
        config = make_config(missing_policy=MissingSignalPolicy.REQUIRE_QUANT)
        inputs = FusionInputs(llm=make_llm_signal(T0))
        fused = fuse_signals(inputs=inputs, config=config, produced_at=T0)
        assert fused is None

    def test_require_quant_policy_fuses_when_quant_present(self) -> None:
        config = make_config(missing_policy=MissingSignalPolicy.REQUIRE_QUANT)
        inputs = FusionInputs(quant=make_quant_signal(T0))
        fused = fuse_signals(inputs=inputs, config=config, produced_at=T0)
        assert fused is not None
        assert fused.missing_inputs == ["llm", "regime", "memory"]
