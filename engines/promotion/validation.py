"""Deterministic, complete Strategy Validation Factory (INV-1, INV-3, INV-8)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from math import isfinite
from typing import Any, Protocol
from uuid import UUID, uuid4

from core.domain.enums import ExperimentStatus, StrategyState
from core.schemas.base import Provenance
from core.schemas.research_factory import ExperimentRun, StrategyCandidate

__all__ = [
    "ALL_VALIDATION_STAGES",
    "QUANT_MODEL_STAGES",
    "PaperEligibility",
    "StageOutcome",
    "StrategyValidationFactory",
    "StrategyValidationPolicy",
    "StrategyValidationRunner",
    "ValidationReport",
]

ALL_VALIDATION_STAGES = (
    "basic_backtest",
    "transaction_costs",
    "spread",
    "slippage",
    "swap_financing",
    "out_of_sample",
    "walk_forward",
    "purged_validation",
    "embargo",
    "monte_carlo",
    "parameter_perturbation",
    "regime_tests",
    "sensitivity_analysis",
    "multiple_testing_controls",
)
QUANT_MODEL_STAGES = ("factor_diagnostics",)
REQUIRED_PERFORMANCE_METRICS = (
    "cagr",
    "sharpe",
    "sortino",
    "calmar",
    "max_drawdown",
    "profit_factor",
    "expectancy",
    "turnover",
    "tail_loss",
    "stability",
    "regime_dependence",
)
REQUIRED_QUANT_METRICS = ("ic", "rank_ic", "factor_decay", "calibration", "drift_sensitivity")


class StrategyValidationRunner(Protocol):
    """Adapter boundary; runners must use point-in-time inputs supplied in config."""

    def run_stage(
        self, candidate: StrategyCandidate, stage: str, config: Mapping[str, Any]
    ) -> StageOutcome: ...


class ExperimentRecorder(Protocol):
    """Durable sink for every completed or failed validation experiment."""

    def record(self, run: ExperimentRun) -> None: ...


class ValidationLedgerUnavailable(RuntimeError):
    """Fail closed: no eligibility report exists when durable recording is unavailable."""


@dataclass(frozen=True)
class StageOutcome:
    metrics: dict[str, float]
    artifacts: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StrategyValidationPolicy:
    """Thresholds deliberately constrain more than risk-adjusted return."""

    min_cagr: float = 0.0
    min_sharpe: float = 0.0
    min_sortino: float = 0.0
    min_calmar: float = 0.0
    max_drawdown: float = 1.0
    min_profit_factor: float = 1.0
    min_expectancy: float = 0.0
    max_turnover: float = float("inf")
    max_tail_loss: float = 1.0
    min_stability: float = 0.0
    max_regime_dependence: float = 1.0
    min_cost_retention: float = 0.75
    min_perturbation_retention: float = 0.80
    min_monte_carlo_pass_rate: float = 0.80
    max_adjusted_p_value: float = 0.05
    require_embargo: bool = True
    min_walk_forward_windows: int = 1
    min_regimes_tested: int = 3


@dataclass(frozen=True)
class ValidationReport:
    receipt_id: UUID
    strategy_candidate_id: UUID
    eligible_for_paper: bool
    required_stages: tuple[str, ...]
    completed_stages: tuple[str, ...]
    failed_stages: tuple[str, ...]
    experiment_runs: tuple[ExperimentRun, ...]
    reasons: tuple[str, ...]


class PaperEligibility:
    """The only deterministic check used before requesting PAPER promotion."""

    @staticmethod
    def assert_eligible(candidate: StrategyCandidate, report: ValidationReport) -> None:
        if candidate.candidate_id != report.strategy_candidate_id:
            raise ValueError("validation report belongs to a different StrategyCandidate")
        if candidate.state is not StrategyState.ROBUSTNESS_OK:
            raise ValueError("only ROBUSTNESS_OK candidates can be considered for PAPER")
        if set(report.required_stages) != set(report.completed_stages):
            raise ValueError("StrategyCandidate skipped one or more validation stages")
        if not report.eligible_for_paper:
            raise ValueError("StrategyCandidate has not passed every validation stage for PAPER")


class StrategyValidationFactory:
    """Runs every configured stage and persists a canonical ExperimentRun for each attempt."""

    def __init__(
        self,
        runner: StrategyValidationRunner,
        policy: StrategyValidationPolicy,
        recorder: ExperimentRecorder,
    ) -> None:
        self._runner = runner
        self._policy = policy
        self._recorder = recorder

    def validate(
        self,
        candidate: StrategyCandidate,
        config: Mapping[str, Any],
        *,
        dataset_ref: str,
        dataset_hash: str,
        now: datetime,
        is_quant_model: bool | None = None,
    ) -> ValidationReport:
        self._validate_config(config)
        self._validate_candidate_lineage(candidate, dataset_hash)
        # Classification derives from immutable candidate lineage, not caller input.
        del is_quant_model
        stages = (*ALL_VALIDATION_STAGES, *(QUANT_MODEL_STAGES if candidate.model_ids else ()))
        runs: list[ExperimentRun] = []
        failed: list[str] = []
        reasons: list[str] = []
        baseline: StageOutcome | None = None

        for stage in stages:
            try:
                outcome = self._runner.run_stage(candidate, stage, config)
                stage_reasons = self._evaluate(stage, outcome, baseline, bool(candidate.model_ids))
                if stage == "basic_backtest":
                    baseline = outcome
                if stage_reasons:
                    failed.append(stage)
                    reasons.extend(stage_reasons)
                    runs.append(
                        self._run(
                            candidate,
                            stage,
                            config,
                            dataset_ref,
                            dataset_hash,
                            now,
                            outcome,
                            ExperimentStatus.FAILED,
                            stage_reasons,
                        )
                    )
                else:
                    runs.append(
                        self._run(
                            candidate,
                            stage,
                            config,
                            dataset_ref,
                            dataset_hash,
                            now,
                            outcome,
                            ExperimentStatus.COMPLETED,
                            [],
                        )
                    )
            except Exception as exc:
                failed.append(stage)
                reasons.append(f"{stage}: runner failed: {type(exc).__name__}: {exc}")
                runs.append(
                    self._failed_run(candidate, stage, config, dataset_ref, dataset_hash, now, exc)
                )
            try:
                self._recorder.record(runs[-1])
            except Exception as exc:
                raise ValidationLedgerUnavailable(
                    f"validation ledger unavailable while recording {stage}"
                ) from exc
        return ValidationReport(
            receipt_id=uuid4(),
            strategy_candidate_id=candidate.candidate_id,
            eligible_for_paper=not failed and len(runs) == len(stages),
            required_stages=tuple(stages),
            completed_stages=tuple(run.name.removeprefix("validation:") for run in runs),
            failed_stages=tuple(failed),
            experiment_runs=tuple(runs),
            reasons=tuple(reasons),
        )

    def _evaluate(
        self, stage: str, outcome: StageOutcome, baseline: StageOutcome | None, is_quant_model: bool
    ) -> list[str]:
        metrics = outcome.metrics
        reasons: list[str] = []
        if not metrics:
            reasons.append(f"{stage}: missing validation metrics")
        if any(not isfinite(metric) for metric in metrics.values()):
            reasons.append(f"{stage}: non-finite validation metric")
        if not outcome.artifacts:
            reasons.append(f"{stage}: missing validation artifacts")
        if stage == "basic_backtest":
            missing = set(REQUIRED_PERFORMANCE_METRICS) - metrics.keys()
            if missing:
                reasons.append(f"basic_backtest: missing metrics {sorted(missing)}")
            checks = (
                ("cagr", metrics.get("cagr", float("-inf")) >= self._policy.min_cagr),
                ("sharpe", metrics.get("sharpe", float("-inf")) >= self._policy.min_sharpe),
                ("sortino", metrics.get("sortino", float("-inf")) >= self._policy.min_sortino),
                ("calmar", metrics.get("calmar", float("-inf")) >= self._policy.min_calmar),
                (
                    "max_drawdown",
                    metrics.get("max_drawdown", float("inf")) <= self._policy.max_drawdown,
                ),
                (
                    "profit_factor",
                    metrics.get("profit_factor", float("-inf")) >= self._policy.min_profit_factor,
                ),
                (
                    "expectancy",
                    metrics.get("expectancy", float("-inf")) >= self._policy.min_expectancy,
                ),
                ("turnover", metrics.get("turnover", float("inf")) <= self._policy.max_turnover),
                ("tail_loss", metrics.get("tail_loss", float("inf")) <= self._policy.max_tail_loss),
                (
                    "stability",
                    metrics.get("stability", float("-inf")) >= self._policy.min_stability,
                ),
                (
                    "regime_dependence",
                    metrics.get("regime_dependence", float("inf"))
                    <= self._policy.max_regime_dependence,
                ),
            )
            reasons.extend(
                f"basic_backtest: {name} threshold failed" for name, passed in checks if not passed
            )
        if (
            stage in {"transaction_costs", "spread", "slippage", "swap_financing"}
            and baseline is not None
            and metrics.get("cagr", float("-inf"))
            < baseline.metrics.get("cagr", 0.0) * self._policy.min_cost_retention
        ):
            reasons.append(f"{stage}: performance disappears under realistic trading costs")
        if (
            stage in {"parameter_perturbation", "sensitivity_analysis"}
            and metrics.get("cagr_retention", float("-inf"))
            < self._policy.min_perturbation_retention
        ):
            reasons.append(f"{stage}: fragile under small parameter changes")
        if (
            stage == "monte_carlo"
            and metrics.get("pass_rate", float("-inf")) < self._policy.min_monte_carlo_pass_rate
        ):
            reasons.append("monte_carlo: insufficient resampled-trade robustness")
        if stage == "multiple_testing_controls":
            if metrics.get("adjusted_p_value", float("inf")) > self._policy.max_adjusted_p_value:
                reasons.append("multiple_testing_controls: adjusted p-value exceeds policy")
            if metrics.get("experiments_recorded", 0.0) < 1.0:
                reasons.append("multiple_testing_controls: experiment ledger is incomplete")
        if stage == "out_of_sample" and outcome.details.get("out_of_sample") is not True:
            reasons.append("out_of_sample: runner did not prove held-out data")
        if (
            stage == "walk_forward"
            and metrics.get("windows", 0.0) < self._policy.min_walk_forward_windows
        ):
            reasons.append("walk_forward: insufficient chronological forward windows")
        if stage == "purged_validation" and metrics.get("purge_gap", 0.0) <= 0.0:
            reasons.append("purged_validation: no positive purge gap")
        if stage == "embargo":
            if outcome.details.get("applicable") is False:
                if self._policy.require_embargo:
                    reasons.append("embargo: policy requires embargo")
                elif not outcome.details.get("reason"):
                    reasons.append("embargo: inapplicability requires a recorded reason")
            elif metrics.get("embargo_period", 0.0) <= 0.0:
                reasons.append("embargo: no positive embargo period")
        if (
            stage == "regime_tests"
            and metrics.get("regimes_tested", 0.0) < self._policy.min_regimes_tested
        ):
            reasons.append("regime_tests: insufficient regime coverage")
        if stage == "factor_diagnostics" and is_quant_model:
            missing = set(REQUIRED_QUANT_METRICS) - metrics.keys()
            if missing:
                reasons.append(f"factor_diagnostics: missing metrics {sorted(missing)}")
        return reasons

    @staticmethod
    def _validate_config(config: Mapping[str, Any]) -> None:
        as_of = config.get("as_of")
        if not isinstance(as_of, datetime) or as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("validation config requires timezone-aware as_of datetime")
        seed = config.get("seed")
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise ValueError("validation config requires integer seed")
        if not config.get("config_hash"):
            raise ValueError("validation config requires config_hash")
        cutoff = config.get("data_max_timestamp")
        if not isinstance(cutoff, datetime) or cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError("validation config requires timezone-aware data_max_timestamp")
        if cutoff > as_of:
            raise ValueError("validation data_max_timestamp must not be after as_of")

    @staticmethod
    def _validate_candidate_lineage(candidate: StrategyCandidate, dataset_hash: str) -> None:
        if not candidate.code_sha or not candidate.dependencies or not candidate.llm_metadata:
            raise ValueError(
                "validation requires StrategyCandidate code and dependency/LLM lineage"
            )
        if not dataset_hash.startswith("sha256:") or len(dataset_hash) != 71:
            raise ValueError("validation requires sha256 dataset_hash")

    @staticmethod
    def _run(
        candidate: StrategyCandidate,
        stage: str,
        config: Mapping[str, Any],
        dataset_ref: str,
        dataset_hash: str,
        now: datetime,
        outcome: StageOutcome,
        status: ExperimentStatus,
        reasons: list[str],
    ) -> ExperimentRun:
        return ExperimentRun(
            experiment_id=uuid4(),
            name=f"validation:{stage}",
            experiment_type="STRATEGY_VALIDATION",
            config=dict(config),
            dataset_ref=dataset_ref,
            dataset_hash=dataset_hash,
            code_sha=candidate.code_sha,
            config_hash=str(config["config_hash"]),
            seed=int(config["seed"]),
            environment_pin={},
            status=status,
            started_at=now,
            finished_at=now,
            results={"stage": stage, "reasons": reasons, **outcome.details},
            metrics=outcome.metrics,
            artifacts=outcome.artifacts or ["inline://validation-result"],
            dependencies=candidate.dependencies,
            llm_metadata=candidate.llm_metadata,
            produced_at=now,
            provenance=Provenance(producer="strategy-validation-factory", produced_at=now),
        )

    @staticmethod
    def _failed_run(
        candidate: StrategyCandidate,
        stage: str,
        config: Mapping[str, Any],
        dataset_ref: str,
        dataset_hash: str,
        now: datetime,
        exc: Exception,
    ) -> ExperimentRun:
        return StrategyValidationFactory._run(
            candidate,
            stage,
            config,
            dataset_ref,
            dataset_hash,
            now,
            StageOutcome({}, ["inline://validation-error"], {"error": str(exc)}),
            ExperimentStatus.FAILED,
            [f"runner failure: {type(exc).__name__}"],
        )
