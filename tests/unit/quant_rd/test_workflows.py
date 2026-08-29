from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from adapters.qlib import QlibAdapter
from adapters.rdagent import RDAgentAdapter
from core.domain.enums import StrategyState
from core.schemas.base import DomainObject
from core.schemas.research_factory import ExperimentRun
from services.quant_rd.policy import ResearchAuthorityPolicy
from services.quant_rd.workflows import QuantResearchWorkflows


class FakeRDAgent:
    def generate_hypothesis(self, kind: str, context: Any) -> dict[str, Any]:
        return {"kind": kind, "title": f"{kind} idea", "rationale": "point-in-time signal"}

    def implement(self, hypothesis: Any) -> dict[str, Any]:
        kind = str(hypothesis["kind"])
        return {
            "kind": kind,
            "name": f"candidate_{kind}",
            "code": f"def {kind}(frame): return frame.shift(1)",
            "parameters": {"model_type": "LightGBM"},
            "llm_metadata": {"model": "test-llm", "temperature": 0},
        }


class FakeQlib:
    def test_factor(self, code: str, config: Any) -> dict[str, Any]:
        return {"metrics": {"ic": 0.03, "rank_ic": 0.04}, "artifacts": ["factor.json"]}

    def test_model(self, code: str, config: Any) -> dict[str, Any]:
        return {"metrics": {"mse": 0.2}, "artifacts": ["model.bin"]}

    def evaluate_strategy(self, config: Any) -> dict[str, Any]:
        return {"metrics": {"sharpe_after_costs": 1.1}, "artifacts": ["strategy.json"]}


class FailingQlib(FakeQlib):
    def test_factor(self, code: str, config: Any) -> dict[str, Any]:
        raise RuntimeError("experiment failed")


class MemoryStore:
    def __init__(self) -> None:
        self.values: list[DomainObject] = []

    def append(self, value: DomainObject) -> str:
        self.values.append(value)
        return f"memory://{len(self.values)}"


class MemoryTracker:
    def __init__(self) -> None:
        self.runs: list[ExperimentRun] = []

    def log(self, run: ExperimentRun) -> None:
        self.runs.append(run)


def test_all_seven_workflow_stages_produce_canonical_outputs(fixed_start, tmp_path: Path) -> None:
    store = MemoryStore()
    tracker = MemoryTracker()
    workflows = QuantResearchWorkflows(
        RDAgentAdapter(FakeRDAgent()),
        QlibAdapter(FakeQlib()),
        store,
        tracker,
        ResearchAuthorityPolicy(tmp_path / "workspace", tmp_path / "outputs"),
        {"rdagent": "0.8.0", "pyqlib": "0.9.7", "mlflow": "3.8.1"},
    )
    config = {"as_of": "2025-12-31T00:00:00Z", "seed": 42, "purge_days": 5}
    dataset_hash = "sha256:" + "d" * 64

    factor_hypothesis = workflows.factor_hypothesis_generation({"universe": "EURUSD"})
    factor_impl = workflows.factor_implementation(factor_hypothesis)
    factor, factor_run = workflows.factor_testing(
        factor_impl,
        config,
        dataset_ref="ds://eurusd/v1",
        dataset_hash=dataset_hash,
        now=fixed_start,
    )
    model_hypothesis = workflows.model_hypothesis_generation({"factors": [factor.name]})
    model_impl = workflows.model_implementation(model_hypothesis)
    model, model_run = workflows.model_testing(
        model_impl,
        config,
        dataset_ref="ds://eurusd/v1",
        dataset_hash=dataset_hash,
        now=fixed_start,
    )
    strategy, strategy_run = workflows.experiment_evaluation(
        "factor-model-ensemble",
        [factor],
        [model],
        config,
        dataset_ref="ds://eurusd/v1",
        dataset_hash=dataset_hash,
        now=fixed_start,
    )

    assert factor.rank_ic == 0.04
    assert model.framework == "qlib"
    assert factor_run.dataset_hash == model_run.dataset_hash == dataset_hash
    assert strategy.state is StrategyState.CANDIDATE
    assert len(store.values) == 6
    assert tracker.runs == [factor_run, model_run, strategy_run]


def test_failed_experiment_is_canonical_and_tracked(fixed_start, tmp_path: Path) -> None:
    store = MemoryStore()
    tracker = MemoryTracker()
    workflows = QuantResearchWorkflows(
        RDAgentAdapter(FakeRDAgent()),
        QlibAdapter(FailingQlib()),
        store,
        tracker,
        ResearchAuthorityPolicy(tmp_path / "workspace", tmp_path / "outputs"),
        {"rdagent": "0.8.0", "pyqlib": "0.9.7", "mlflow": "3.8.1"},
    )
    hypothesis = workflows.factor_hypothesis_generation({})
    implementation = workflows.factor_implementation(hypothesis)

    with pytest.raises(RuntimeError, match="experiment failed"):
        workflows.factor_testing(
            implementation,
            {"as_of": "2025-12-31T00:00:00Z", "seed": 1},
            dataset_ref="ds://test/v1",
            dataset_hash="sha256:" + "e" * 64,
            now=fixed_start,
        )

    assert len(store.values) == 1
    assert isinstance(store.values[0], ExperimentRun)
    assert store.values[0].status.value == "FAILED"
    assert tracker.runs == [store.values[0]]
