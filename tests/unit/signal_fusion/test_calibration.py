"""Calibration tests: LLM zeroing, regime-specific weights, determinism (INV-16)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from random import Random

import pytest
from core.domain.enums import SignalDirection
from core.schemas.fusion import FusionInputs
from engines.signal_fusion.calibration import Calibrator, calibrate
from engines.signal_fusion.errors import CalibrationInsufficientDataError
from engines.signal_fusion.evaluation import LabeledFusionCase

from factories import make_llm_signal, make_quant_signal, make_regime_context

T0 = datetime(2026, 1, 5, 10, 0, 0, tzinfo=UTC)
REALIZED = 0.01


def _case(
    t: datetime,
    *,
    quant_dir: SignalDirection | None,
    llm_dir: SignalDirection | None,
    realized: float,
    regime: str | None = None,
) -> LabeledFusionCase:
    inputs = FusionInputs(
        quant=make_quant_signal(t, direction=quant_dir) if quant_dir is not None else None,
        llm=make_llm_signal(t, direction=llm_dir) if llm_dir is not None else None,
        regime=make_regime_context(t, regime=regime) if regime is not None else None,
    )
    return LabeledFusionCase(inputs=inputs, realized_return=realized, as_of=t)


def _noisy_llm_cases(n: int = 120, seed: int = 7) -> list[LabeledFusionCase]:
    """Quant is 60% accurate; the LLM is pure noise."""
    rng = Random(seed)
    cases: list[LabeledFusionCase] = []
    for i in range(n):
        t = T0 + timedelta(minutes=i)
        quant_dir = SignalDirection.LONG if rng.random() < 0.6 else SignalDirection.SHORT
        realized = REALIZED if quant_dir is SignalDirection.LONG else -REALIZED
        llm_dir = SignalDirection.LONG if rng.random() < 0.5 else SignalDirection.SHORT
        cases.append(_case(t, quant_dir=quant_dir, llm_dir=llm_dir, realized=realized))
    return cases


def _skilled_llm_cases(n: int = 200, seed: int = 11) -> list[LabeledFusionCase]:
    """Quant is 55% accurate; the LLM is 90% accurate."""
    rng = Random(seed)
    cases: list[LabeledFusionCase] = []
    for i in range(n):
        t = T0 + timedelta(minutes=i)
        llm_dir = SignalDirection.LONG if rng.random() < 0.5 else SignalDirection.SHORT
        realized = REALIZED if (rng.random() < 0.9) else -REALIZED
        if llm_dir is SignalDirection.SHORT:
            realized = -realized
        quant_dir = (
            SignalDirection.LONG
            if (rng.random() < 0.55) == (realized > 0)
            else SignalDirection.SHORT
        )
        cases.append(_case(t, quant_dir=quant_dir, llm_dir=llm_dir, realized=realized))
    return cases


class TestLlmWeightZeroing:
    def test_noisy_llm_gets_zero_weight(self) -> None:
        artifact = calibrate(
            _noisy_llm_cases(), name="noisy-llm", trained_at=T0, weight_step_bp=500
        )
        assert artifact.llm_added_value is False
        assert artifact.llm_weight_bp == 0
        assert artifact.config.default_weights.llm_bp == 0
        assert "zero" in " ".join(artifact.selection_notes).lower()

    def test_skilled_llm_keeps_weight(self) -> None:
        artifact = calibrate(
            _skilled_llm_cases(), name="skilled-llm", trained_at=T0, weight_step_bp=500
        )
        assert artifact.llm_added_value is True
        assert artifact.llm_weight_bp > 0
        assert artifact.config.default_weights.llm_bp == artifact.llm_weight_bp


class TestRegimeSpecificCalibration:
    def test_regime_specific_weights_learned(self) -> None:
        rng = Random(3)
        cases: list[LabeledFusionCase] = []
        for i in range(60):
            t = T0 + timedelta(minutes=i)
            quant_dir = SignalDirection.LONG if rng.random() < 0.5 else SignalDirection.SHORT
            llm_dir = SignalDirection.LONG if rng.random() < 0.5 else SignalDirection.SHORT
            cases.append(
                _case(
                    t,
                    quant_dir=quant_dir,
                    llm_dir=llm_dir,
                    realized=REALIZED if quant_dir is SignalDirection.LONG else -REALIZED,
                    regime="trust_quant",
                )
            )
        for i in range(60):
            t = T0 + timedelta(minutes=i, seconds=30)
            quant_dir = SignalDirection.LONG if rng.random() < 0.5 else SignalDirection.SHORT
            llm_dir = SignalDirection.LONG if rng.random() < 0.5 else SignalDirection.SHORT
            cases.append(
                _case(
                    t,
                    quant_dir=quant_dir,
                    llm_dir=llm_dir,
                    realized=REALIZED if llm_dir is SignalDirection.LONG else -REALIZED,
                    regime="trust_llm",
                )
            )
        artifact = calibrate(
            cases,
            name="regime-split",
            trained_at=T0,
            weight_step_bp=500,
            min_cases_per_regime=50,
        )
        assert "trust_quant" in artifact.config.regime_weights
        assert "trust_llm" in artifact.config.regime_weights
        assert artifact.config.regime_weights["trust_quant"].quant_bp == 10000
        # In trust_llm the LLM carries the signal; the tie-break keeps as much
        # quant weight as possible among equally-perfect combinations.
        trust_llm = artifact.config.regime_weights["trust_llm"]
        assert trust_llm.llm_bp > 0
        assert trust_llm.llm_bp > trust_llm.quant_bp

    def test_small_regime_falls_back_to_default(self) -> None:
        rng = Random(5)
        cases: list[LabeledFusionCase] = []
        for i in range(60):
            t = T0 + timedelta(minutes=i)
            quant_dir = SignalDirection.LONG if rng.random() < 0.5 else SignalDirection.SHORT
            cases.append(
                _case(
                    t,
                    quant_dir=quant_dir,
                    llm_dir=SignalDirection.LONG,
                    realized=REALIZED if quant_dir is SignalDirection.LONG else -REALIZED,
                    regime="rare_regime" if i < 5 else None,
                )
            )
        artifact = calibrate(
            cases,
            name="rare-regime",
            trained_at=T0,
            weight_step_bp=500,
            min_cases_per_regime=20,
        )
        assert "rare_regime" not in artifact.config.regime_weights
        assert any("rare_regime" in note for note in artifact.selection_notes)


class TestCalibrationDeterminism:
    def test_same_data_same_artifact(self) -> None:
        cases = _noisy_llm_cases(seed=21)
        first = Calibrator(weight_step_bp=500, min_cases_confidence=10).calibrate(
            cases, name="det", trained_at=T0
        )
        second = Calibrator(weight_step_bp=500, min_cases_confidence=10).calibrate(
            cases, name="det", trained_at=T0
        )
        assert first.calibration_version == second.calibration_version
        assert first.artifact_id == second.artifact_id
        assert first.config.model_dump_json() == second.config.model_dump_json()

    def test_confidence_maps_are_monotone(self) -> None:
        artifact = calibrate(_noisy_llm_cases(), name="mono", trained_at=T0, weight_step_bp=500)
        for name, calibration in artifact.config.confidence_calibration.items():
            assert calibration.y == sorted(calibration.y), name


class TestCalibrationErrors:
    def test_empty_cases_rejected(self) -> None:
        with pytest.raises(CalibrationInsufficientDataError):
            Calibrator().calibrate([], name="empty", trained_at=T0)

    def test_invalid_weight_step_rejected(self) -> None:
        with pytest.raises(CalibrationInsufficientDataError, match="divide"):
            Calibrator(weight_step_bp=300)

    def test_weights_sum_exactly_in_every_regime(self) -> None:
        artifact = calibrate(_noisy_llm_cases(), name="sum", trained_at=T0, weight_step_bp=500)
        assert sum(artifact.config.default_weights.as_dict().values()) == 10000
        for weights in artifact.config.regime_weights.values():
            assert sum(weights.as_dict().values()) == 10000
