"""Autonomous factor/model R&D pipeline with canonical outputs only."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import uuid4

from adapters.qlib import EvaluationResult, QlibAdapter
from adapters.rdagent import Hypothesis, Implementation, RDAgentAdapter
from core.domain.enums import CandidateStatus, ExperimentStatus, StrategyState
from core.schemas.base import Provenance
from core.schemas.research_factory import (
    ExperimentRun,
    FactorCandidate,
    ModelCandidate,
    StrategyCandidate,
)

from services.quant_rd.lineage import config_hash, content_hash
from services.quant_rd.policy import ResearchAuthorityPolicy
from services.quant_rd.store import CandidateStore
from services.quant_rd.tracking import ExperimentTracker


class QuantResearchWorkflows:
    """Seven explicit workflow stages; none exposes promotion or execution."""

    def __init__(
        self,
        rdagent: RDAgentAdapter,
        qlib: QlibAdapter,
        store: CandidateStore,
        tracker: ExperimentTracker,
        policy: ResearchAuthorityPolicy,
        dependencies: Mapping[str, str],
    ) -> None:
        self._rdagent = rdagent
        self._qlib = qlib
        self._store = store
        self._tracker = tracker
        self._policy = policy
        self._dependencies = dict(dependencies)

    def factor_hypothesis_generation(self, context: Mapping[str, Any]) -> Hypothesis:
        return self._rdagent.generate_hypothesis("factor", context)

    def factor_implementation(self, hypothesis: Hypothesis) -> Implementation:
        return self._rdagent.implement(hypothesis)

    def factor_testing(
        self,
        implementation: Implementation,
        config: Mapping[str, Any],
        *,
        dataset_ref: str,
        dataset_hash: str,
        now: datetime,
    ) -> tuple[FactorCandidate, ExperimentRun]:
        self._validate_inputs(config, dataset_hash)
        common = self._lineage(implementation, config, dataset_hash)
        try:
            result = self._qlib.test_factor(implementation.code, config)
        except Exception as exc:
            self._record_failure("FACTOR", implementation, config, dataset_ref, now, common, exc)
            raise
        run = self._experiment("FACTOR", implementation, result, config, dataset_ref, now, common)
        candidate = FactorCandidate(
            candidate_id=uuid4(),
            name=implementation.name,
            description=f"RD-Agent factor: {implementation.name}",
            status=CandidateStatus.VALIDATED,
            generated_by_run=str(run.experiment_id),
            produced_at=now,
            provenance=self._provenance(now, run),
            **common,
            metrics=result.metrics,
            artifacts=result.artifacts,
            ic=result.metrics.get("ic"),
            rank_ic=result.metrics.get("rank_ic"),
        )
        self._record(candidate, run)
        return candidate, run

    def model_hypothesis_generation(self, context: Mapping[str, Any]) -> Hypothesis:
        return self._rdagent.generate_hypothesis("model", context)

    def model_implementation(self, hypothesis: Hypothesis) -> Implementation:
        return self._rdagent.implement(hypothesis)

    def model_testing(
        self,
        implementation: Implementation,
        config: Mapping[str, Any],
        *,
        dataset_ref: str,
        dataset_hash: str,
        now: datetime,
    ) -> tuple[ModelCandidate, ExperimentRun]:
        self._validate_inputs(config, dataset_hash)
        common = self._lineage(implementation, config, dataset_hash)
        try:
            result = self._qlib.test_model(implementation.code, config)
        except Exception as exc:
            self._record_failure("MODEL", implementation, config, dataset_ref, now, common, exc)
            raise
        run = self._experiment("MODEL", implementation, result, config, dataset_ref, now, common)
        candidate = ModelCandidate(
            candidate_id=uuid4(),
            name=implementation.name,
            model_type=str(implementation.parameters.get("model_type", implementation.name)),
            framework="qlib",
            hyperparameters=implementation.parameters,
            training_dataset_ref=dataset_ref,
            seed=int(config["seed"]),
            status=CandidateStatus.VALIDATED,
            produced_by_run=str(run.experiment_id),
            produced_at=now,
            provenance=self._provenance(now, run),
            **common,
            code_ref=result.artifacts[0] if result.artifacts else None,
            metrics=result.metrics,
            artifacts=result.artifacts,
        )
        self._record(candidate, run)
        return candidate, run

    def experiment_evaluation(
        self,
        name: str,
        factors: list[FactorCandidate],
        models: list[ModelCandidate],
        config: Mapping[str, Any],
        *,
        dataset_ref: str,
        dataset_hash: str,
        now: datetime,
    ) -> tuple[StrategyCandidate, ExperimentRun]:
        self._policy.assert_strategy_state(StrategyState.CANDIDATE)
        self._validate_inputs(config, dataset_hash)
        evaluation = self._qlib.evaluate_strategy(config)
        code_hashes = [*(f.code_sha for f in factors), *(m.code_sha for m in models)]
        config_hashes = [*(f.config_hash for f in factors), *(m.config_hash for m in models)]
        combined_dataset_hash = dataset_hash
        combined_code_hash = self._one_hash(code_hashes)
        combined_config_hash = self._one_hash(config_hashes)
        run = ExperimentRun(
            experiment_id=uuid4(),
            name=f"strategy:{name}",
            experiment_type="STRATEGY",
            config=dict(config),
            dataset_ref=dataset_ref,
            dataset_hash=dataset_hash,
            code_sha=combined_code_hash,
            config_hash=combined_config_hash,
            seed=int(config["seed"]),
            environment_pin={"python": "3.11", **self._dependencies},
            status=ExperimentStatus.COMPLETED,
            started_at=now,
            finished_at=now,
            results=evaluation.details,
            metrics=evaluation.metrics,
            artifacts=evaluation.artifacts,
            dependencies=self._dependencies,
            llm_metadata={
                "factor_runs": [item.llm_metadata for item in factors],
                "model_runs": [item.llm_metadata for item in models],
            },
            produced_at=now,
            provenance=Provenance(producer="quant-rd", produced_at=now),
        )
        strategy = StrategyCandidate(
            candidate_id=uuid4(),
            name=name,
            state=StrategyState.CANDIDATE,
            factor_ids=[str(item.candidate_id) for item in factors],
            model_ids=[str(item.candidate_id) for item in models],
            code_sha=combined_code_hash,
            data_hash=combined_dataset_hash,
            dataset_hash=combined_dataset_hash,
            config_hash=combined_config_hash,
            metrics=evaluation.metrics,
            dependencies=self._dependencies,
            llm_metadata={
                "factor_runs": [item.llm_metadata for item in factors],
                "model_runs": [item.llm_metadata for item in models],
            },
            artifacts=[
                artifact
                for artifacts in [
                    *(item.artifacts for item in factors),
                    *(item.artifacts for item in models),
                ]
                for artifact in artifacts
            ],
            evidence=[str(run.experiment_id)],
            originated_from="quant-rd",
            produced_at=now,
            provenance=Provenance(producer="quant-rd", produced_at=now),
        )
        self._store.append(strategy)
        self._store.append(run)
        self._tracker.log(run)
        return strategy, run

    def _lineage(
        self, impl: Implementation, config: Mapping[str, Any], dataset_hash: str
    ) -> dict[str, Any]:
        return {
            "code_sha": content_hash(impl.code),
            "dataset_hash": dataset_hash,
            "config_hash": config_hash(config),
            "dependencies": self._dependencies,
            "llm_metadata": impl.llm_metadata,
        }

    def _experiment(
        self,
        kind: str,
        impl: Implementation,
        result: EvaluationResult,
        config: Mapping[str, Any],
        dataset_ref: str,
        now: datetime,
        lineage: Mapping[str, Any],
    ) -> ExperimentRun:
        return ExperimentRun(
            experiment_id=uuid4(),
            name=f"{kind.lower()}:{impl.name}",
            experiment_type=kind,
            config=dict(config),
            dataset_ref=dataset_ref,
            status=ExperimentStatus.COMPLETED,
            started_at=now,
            finished_at=now,
            seed=int(config["seed"]),
            results=result.details,
            metrics=result.metrics,
            artifacts=result.artifacts,
            environment_pin={"python": "3.11", **self._dependencies},
            produced_at=now,
            provenance=Provenance(producer="quant-rd", produced_at=now),
            **lineage,
        )

    def _record(self, candidate: FactorCandidate | ModelCandidate, run: ExperimentRun) -> None:
        self._store.append(candidate)
        self._store.append(run)
        self._tracker.log(run)

    def _record_failure(
        self,
        kind: str,
        impl: Implementation,
        config: Mapping[str, Any],
        dataset_ref: str,
        now: datetime,
        lineage: Mapping[str, Any],
        error: Exception,
    ) -> None:
        run = ExperimentRun(
            experiment_id=uuid4(),
            name=f"{kind.lower()}:{impl.name}",
            experiment_type=kind,
            config=dict(config),
            dataset_ref=dataset_ref,
            status=ExperimentStatus.FAILED,
            started_at=now,
            finished_at=now,
            seed=int(config["seed"]),
            results={"error_type": type(error).__name__, "error": str(error)},
            artifacts=["inline://experiment-error"],
            environment_pin={"python": "3.11", **self._dependencies},
            produced_at=now,
            provenance=Provenance(producer="quant-rd", produced_at=now),
            **lineage,
        )
        self._store.append(run)
        self._tracker.log(run)

    @staticmethod
    def _validate_inputs(config: Mapping[str, Any], dataset_hash: str) -> None:
        if not config.get("as_of"):
            raise ValueError("point-in-time research config requires as_of")
        if "seed" not in config:
            raise ValueError("reproducible research config requires seed")
        if not dataset_hash.startswith("sha256:") or len(dataset_hash) != 71:
            raise ValueError("dataset_hash must be sha256:<64 lowercase hex characters>")
        try:
            int(dataset_hash.removeprefix("sha256:"), 16)
        except ValueError as exc:
            raise ValueError("dataset_hash must contain hexadecimal data") from exc

    @staticmethod
    def _provenance(now: datetime, run: ExperimentRun) -> Provenance:
        return Provenance(
            producer="quant-rd",
            produced_at=now,
            source_ids={"experiment_id": str(run.experiment_id)},
        )

    @staticmethod
    def _one_hash(values: list[str | None]) -> str | None:
        present = sorted({value for value in values if value})
        return content_hash("".join(present)) if present else None
