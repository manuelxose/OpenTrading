"""Research evaluation: Quant-only vs LLM-only vs Quant+LLM vs baseline."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from core.domain.enums import SignalDirection
from core.schemas.fusion import FusionInputs
from engines.signal_fusion.config import ComponentWeights, FusionConfig
from engines.signal_fusion.errors import CalibrationInsufficientDataError
from engines.signal_fusion.evaluation import (
    CONFIG_COMPARISON_ORDER,
    LabeledFusionCase,
    evaluate_cases,
)

from factories import make_llm_signal, make_quant_signal

T0 = datetime(2026, 1, 5, 10, 0, 0, tzinfo=UTC)


def make_config() -> FusionConfig:
    return FusionConfig(
        name="eval-config",
        version="cal-eval-1",
        default_weights=ComponentWeights(quant_bp=6000, llm_bp=4000, regime_bp=0, memory_bp=0),
    )


def _case(
    t: datetime,
    quant_dir: SignalDirection,
    llm_dir: SignalDirection,
    realized: float,
) -> LabeledFusionCase:
    inputs = FusionInputs(
        quant=make_quant_signal(t, direction=quant_dir, strength=0.8),
        llm=make_llm_signal(t, direction=llm_dir, strength=0.6),
    )
    return LabeledFusionCase(inputs=inputs, realized_return=realized, as_of=t)


class TestMandatoryComparison:
    def test_all_four_configs_reported(self) -> None:
        cases = [
            _case(T0, SignalDirection.LONG, SignalDirection.SHORT, 0.01),
            _case(T0 + timedelta(minutes=1), SignalDirection.SHORT, SignalDirection.LONG, -0.01),
        ]
        report = evaluate_cases(cases, config=make_config(), evaluated_at=T0)
        assert [m.config_name for m in report.metrics] == list(CONFIG_COMPARISON_ORDER)

    def test_quant_only_wins_when_quant_is_perfect(self) -> None:
        cases = [
            _case(T0, SignalDirection.LONG, SignalDirection.SHORT, 0.01),
            _case(T0 + timedelta(minutes=1), SignalDirection.SHORT, SignalDirection.LONG, -0.01),
        ]
        report = evaluate_cases(cases, config=make_config(), evaluated_at=T0)
        by_name = {m.config_name: m for m in report.metrics}
        assert by_name["quant_only"].directional_accuracy == pytest.approx(1.0)
        assert by_name["llm_only"].directional_accuracy == pytest.approx(0.0)
        assert by_name["quant_only"].mean_return == pytest.approx(0.01)
        assert report.winner == "quant_only"

    def test_llm_only_wins_when_llm_is_perfect(self) -> None:
        cases = [
            _case(T0, SignalDirection.SHORT, SignalDirection.LONG, 0.01),
            _case(T0 + timedelta(minutes=1), SignalDirection.LONG, SignalDirection.SHORT, -0.01),
        ]
        report = evaluate_cases(cases, config=make_config(), evaluated_at=T0)
        assert report.winner == "llm_only"

    def test_baseline_is_equal_weight_average(self) -> None:
        cases = [
            _case(T0, SignalDirection.LONG, SignalDirection.LONG, 0.01),
            _case(T0 + timedelta(minutes=1), SignalDirection.SHORT, SignalDirection.SHORT, -0.01),
        ]
        report = evaluate_cases(cases, config=make_config(), evaluated_at=T0)
        baseline = next(m for m in report.metrics if m.config_name == "baseline")
        assert baseline.component_weights == {"quant": 5000, "llm": 5000}
        assert baseline.directional_accuracy == pytest.approx(1.0)

    def test_quant_plus_llm_uses_calibrated_weights(self) -> None:
        cases = [
            _case(T0, SignalDirection.LONG, SignalDirection.LONG, 0.01),
        ]
        report = evaluate_cases(cases, config=make_config(), evaluated_at=T0)
        merged = next(m for m in report.metrics if m.config_name == "quant_plus_llm")
        assert merged.component_weights == {"quant": 6000, "llm": 4000, "regime": 0, "memory": 0}

    def test_flat_predictions_never_count_as_hits(self) -> None:
        # quant perfectly flat predicts nothing; realized moves up.
        inputs = FusionInputs(
            quant=make_quant_signal(T0, direction=SignalDirection.FLAT),
            llm=make_llm_signal(T0, direction=SignalDirection.FLAT),
        )
        case = LabeledFusionCase(inputs=inputs, realized_return=0.01, as_of=T0)
        report = evaluate_cases([case], config=make_config(), evaluated_at=T0)
        quant_only = next(m for m in report.metrics if m.config_name == "quant_only")
        assert quant_only.directional_accuracy == pytest.approx(0.0)
        assert quant_only.n_flat == 1

    def test_empty_cases_rejected(self) -> None:
        with pytest.raises(CalibrationInsufficientDataError):
            evaluate_cases([], config=make_config(), evaluated_at=T0)

    def test_report_is_deterministic(self) -> None:
        cases = [
            _case(T0, SignalDirection.LONG, SignalDirection.SHORT, 0.01),
            _case(T0 + timedelta(minutes=1), SignalDirection.SHORT, SignalDirection.LONG, -0.01),
        ]
        first = evaluate_cases(cases, config=make_config(), evaluated_at=T0)
        second = evaluate_cases(cases, config=make_config(), evaluated_at=T0)
        assert first.report_id == second.report_id
        assert first.model_dump_json() == second.model_dump_json()
