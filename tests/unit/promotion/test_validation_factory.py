from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from core.domain.enums import PromotionAction, StrategyState
from core.schemas.base import Provenance
from core.schemas.promotion import PromotionDecision
from engines.promotion.validation import (
    ALL_VALIDATION_STAGES,
    QUANT_MODEL_STAGES,
    PaperEligibility,
    StageOutcome,
    StrategyValidationFactory,
    StrategyValidationPolicy,
)
from tests.factories import make_strategy_candidate

NOW = datetime(2026, 1, 5, 10, tzinfo=UTC)
DATASET_HASH = "sha256:" + "d" * 64


def baseline_metrics() -> dict[str, float]:
    return {
        "cagr": 0.20,
        "sharpe": 1.2,
        "sortino": 1.4,
        "calmar": 0.9,
        "max_drawdown": 0.22,
        "profit_factor": 1.3,
        "expectancy": 0.01,
        "turnover": 0.8,
        "tail_loss": 0.12,
        "stability": 0.7,
        "regime_dependence": 0.3,
    }


class CompleteRunner:
    def __init__(self, fragile: bool = False, fail_stage: str | None = None) -> None:
        self.fragile = fragile
        self.fail_stage = fail_stage

    def run_stage(self, candidate, stage, config):
        if stage == self.fail_stage:
            raise RuntimeError("simulated runner failure")
        metrics = baseline_metrics() if stage == "basic_backtest" else {"cagr": 0.19}
        if stage in {"parameter_perturbation", "sensitivity_analysis"}:
            metrics = {"cagr_retention": 0.20 if self.fragile else 0.95}
        elif stage == "monte_carlo":
            metrics = {"pass_rate": 0.95}
        elif stage == "multiple_testing_controls":
            metrics = {"adjusted_p_value": 0.01, "experiments_recorded": 12.0}
        elif stage == "walk_forward":
            metrics = {"windows": 3.0}
        elif stage == "purged_validation":
            metrics = {"purge_gap": 5.0}
        elif stage == "embargo":
            metrics = {"embargo_period": 5.0}
        elif stage == "regime_tests":
            metrics = {"regimes_tested": 6.0}
        elif stage == "factor_diagnostics":
            metrics = {
                "ic": 0.03,
                "rank_ic": 0.04,
                "factor_decay": 0.1,
                "calibration": 0.9,
                "drift_sensitivity": 0.2,
            }
        details = {"out_of_sample": True} if stage == "out_of_sample" else {}
        return StageOutcome(metrics, [f"artifact://{stage}.json"], details)


class Recorder:
    def __init__(self) -> None:
        self.runs = []

    def record(self, run) -> None:
        self.runs.append(run)


def candidate(*, quant: bool = False):
    return make_strategy_candidate(
        NOW,
        state=StrategyState.ROBUSTNESS_OK,
        code_sha="a" * 40,
        dependencies={"pyqlib": "0.9.7"},
        llm_metadata={"model": "test"},
        model_ids=["model-1"] if quant else [],
    )


def config() -> dict[str, object]:
    return {
        "as_of": NOW,
        "data_max_timestamp": NOW,
        "seed": 7,
        "config_hash": "sha256:cfg",
    }


def test_complete_quant_validation_records_every_stage_and_allows_paper() -> None:
    proposed = candidate(quant=True)
    recorder = Recorder()
    factory = StrategyValidationFactory(CompleteRunner(), StrategyValidationPolicy(), recorder)
    report = factory.validate(
        proposed,
        config(),
        dataset_ref="ds://test/v1",
        dataset_hash=DATASET_HASH,
        now=NOW,
        is_quant_model=True,
    )

    assert report.eligible_for_paper
    assert set(report.completed_stages) == {*ALL_VALIDATION_STAGES, *QUANT_MODEL_STAGES}
    assert len(report.experiment_runs) == len(report.required_stages)
    assert recorder.runs == list(report.experiment_runs)
    assert {run.status.value for run in report.experiment_runs} == {"COMPLETED"}
    PaperEligibility.assert_eligible(proposed, report)


def test_fragile_candidate_is_rejected_even_with_good_sharpe() -> None:
    proposed = candidate()
    factory = StrategyValidationFactory(
        CompleteRunner(fragile=True), StrategyValidationPolicy(), Recorder()
    )
    report = factory.validate(
        proposed,
        config(),
        dataset_ref="ds://test/v1",
        dataset_hash=DATASET_HASH,
        now=NOW,
        is_quant_model=False,
    )

    assert not report.eligible_for_paper
    assert {"parameter_perturbation", "sensitivity_analysis"} <= set(report.failed_stages)
    with pytest.raises(ValueError, match="not passed every validation"):
        PaperEligibility.assert_eligible(proposed, report)


def test_runner_failure_is_recorded_and_blocks_paper() -> None:
    proposed = candidate()
    recorder = Recorder()
    report = StrategyValidationFactory(
        CompleteRunner(fail_stage="walk_forward"), StrategyValidationPolicy(), recorder
    ).validate(
        proposed,
        config(),
        dataset_ref="ds://test/v1",
        dataset_hash=DATASET_HASH,
        now=NOW,
        is_quant_model=False,
    )

    failed = next(run for run in report.experiment_runs if run.name == "validation:walk_forward")
    assert failed.status.value == "FAILED"
    assert failed in recorder.runs
    with pytest.raises(ValueError, match="not passed every validation"):
        PaperEligibility.assert_eligible(proposed, report)


def test_paper_promotion_cannot_skip_validation_receipt() -> None:
    with pytest.raises(ValueError, match="Validation Factory receipt"):
        PromotionDecision(
            decision_id=uuid4(),
            strategy_candidate_id=uuid4(),
            from_state=StrategyState.ROBUSTNESS_OK,
            to_state=StrategyState.PAPER,
            decision=PromotionAction.APPROVE,
            requested_by="promotion-engine",
            approved_by="deterministic-promotion-gate",
            produced_at=NOW,
            provenance=Provenance(producer="promotion-engine", produced_at=NOW),
        )


def test_paper_promotion_rejects_a_forged_receipt() -> None:
    with pytest.raises(ValueError, match="validated promotion service"):
        PromotionDecision(
            decision_id=uuid4(),
            strategy_candidate_id=uuid4(),
            from_state=StrategyState.ROBUSTNESS_OK,
            to_state=StrategyState.PAPER,
            decision=PromotionAction.APPROVE,
            validation_receipt_id=uuid4(),
            requested_by="promotion-engine",
            approved_by="deterministic-promotion-gate",
            produced_at=NOW,
            provenance=Provenance(producer="promotion-engine", produced_at=NOW),
        )


def test_live_auto_promotion_requires_the_administrative_registry() -> None:
    # INV-8 / Phase 11: strategy code and research pipelines can never
    # self-promote into LIVE_AUTO, even with a structurally valid transition.
    with pytest.raises(ValueError, match="administrative action"):
        PromotionDecision(
            decision_id=uuid4(),
            strategy_candidate_id=uuid4(),
            from_state=StrategyState.LIVE_GATED,
            to_state=StrategyState.LIVE_AUTO,
            decision=PromotionAction.APPROVE,
            requested_by="rd-agent",
            approved_by="rd-agent",
            produced_at=NOW,
            provenance=Provenance(producer="promotion-engine", produced_at=NOW),
        )


def test_nan_robustness_metrics_fail_closed() -> None:
    class NaNRunner(CompleteRunner):
        def run_stage(self, candidate, stage, config):
            outcome = super().run_stage(candidate, stage, config)
            if stage == "monte_carlo":
                return StageOutcome({"pass_rate": float("nan")}, outcome.artifacts)
            return outcome

    proposed = candidate()
    report = StrategyValidationFactory(
        NaNRunner(), StrategyValidationPolicy(), Recorder()
    ).validate(
        proposed,
        config(),
        dataset_ref="ds://test/v1",
        dataset_hash=DATASET_HASH,
        now=NOW,
        is_quant_model=False,
    )
    assert "monte_carlo" in report.failed_stages
    assert not report.eligible_for_paper


def test_model_candidate_always_runs_quant_diagnostics() -> None:
    proposed = candidate(quant=True)
    report = StrategyValidationFactory(
        CompleteRunner(), StrategyValidationPolicy(), Recorder()
    ).validate(
        proposed,
        config(),
        dataset_ref="ds://test/v1",
        dataset_hash=DATASET_HASH,
        now=NOW,
        is_quant_model=False,
    )
    assert "factor_diagnostics" in report.required_stages
