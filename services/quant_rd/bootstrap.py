"""Fail-closed executable composition for autonomous canonical Quant R&D."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from adapters.qlib import QlibAdapter
from adapters.rdagent import NativeRDAgentQlibBackend, RDAgentAdapter
from core.clock import SystemClock

from services.quant_rd.lineage import installed_dependencies
from services.quant_rd.policy import ResearchAuthorityPolicy
from services.quant_rd.store import JsonlCandidateStore
from services.quant_rd.tracking import MlflowExperimentTracker
from services.quant_rd.workflows import QuantResearchWorkflows

ALLOWED_WORKFLOWS = {"fin_factor", "fin_model", "fin_quant"}


def assert_runtime_version() -> None:
    """INV-13: Quant R&D runs on Python 3.11 — the two runtimes are never merged.
    The image pins 3.11 at build time; this runtime assertion makes a
    mis-rebuilt image fail closed instead of silently running on 3.12."""
    if sys.version_info[:2] != (3, 11):
        raise RuntimeError(
            f"Quant R&D requires Python 3.11 (INV-13), "
            f"running {sys.version_info.major}.{sys.version_info.minor}"
        )


def validate_authority_environment(environment: dict[str, str]) -> None:
    if environment.get("OT_OPERATING_MODE", "RESEARCH") != "RESEARCH":
        raise RuntimeError("Quant R&D can run only in RESEARCH mode")
    if environment.get("OT_BROKER_ENABLED", "false").lower() != "false":
        raise RuntimeError("Quant R&D cannot enable a broker connection")
    if environment.get("OT_LIVE_AUTO_ENABLED", "false").lower() != "false":
        raise RuntimeError("Quant R&D cannot enable LIVE_AUTO")
    forbidden = [
        name
        for name in environment
        if ("MT4" in name.upper() or "BROKER" in name.upper()) and name != "OT_BROKER_ENABLED"
    ]
    if forbidden:
        raise RuntimeError("broker/MT4 environment variables are forbidden in Quant R&D")


def run_autonomous_cycle(
    workflows: QuantResearchWorkflows, workflow_name: str, config: dict[str, Any], now: Any
) -> None:
    dataset_ref, dataset_hash = str(config["dataset_ref"]), str(config["dataset_hash"])
    experiment_config = dict(config["experiment"])
    factor = model = None
    if workflow_name in {"fin_factor", "fin_quant"}:
        factor_hypothesis = workflows.factor_hypothesis_generation(config.get("context", {}))
        factor_impl = workflows.factor_implementation(factor_hypothesis)
        factor, _ = workflows.factor_testing(
            factor_impl,
            experiment_config,
            dataset_ref=dataset_ref,
            dataset_hash=dataset_hash,
            now=now,
        )
    if workflow_name in {"fin_model", "fin_quant"}:
        model_hypothesis = workflows.model_hypothesis_generation(config.get("context", {}))
        model_impl = workflows.model_implementation(model_hypothesis)
        model, _ = workflows.model_testing(
            model_impl,
            experiment_config,
            dataset_ref=dataset_ref,
            dataset_hash=dataset_hash,
            now=now,
        )
    if workflow_name == "fin_quant" and factor is not None and model is not None:
        workflows.experiment_evaluation(
            str(config.get("strategy_name", "rdagent-quant-candidate")),
            [factor],
            [model],
            experiment_config,
            dataset_ref=dataset_ref,
            dataset_hash=dataset_hash,
            now=now,
        )


def main(argv: list[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    workflow_name = args[0] if args else "fin_quant"
    if workflow_name not in ALLOWED_WORKFLOWS:
        raise RuntimeError(f"unsupported Quant R&D workflow: {workflow_name}")
    assert_runtime_version()
    validate_authority_environment(dict(os.environ))
    dependencies = installed_dependencies()
    config_path = Path(os.environ.get("OT_RESEARCH_CONFIG", "/workspace/config.json"))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    backend = NativeRDAgentQlibBackend()
    policy = ResearchAuthorityPolicy(Path("/workspace"), Path("/outputs"))
    workflows = QuantResearchWorkflows(
        RDAgentAdapter(backend),
        QlibAdapter(backend),
        JsonlCandidateStore(Path("/outputs"), policy),
        MlflowExperimentTracker(os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000")),
        policy,
        dependencies,
    )
    run_autonomous_cycle(workflows, workflow_name, config, SystemClock().now())


if __name__ == "__main__":
    main()
