from __future__ import annotations

from tests.factories import (
    make_experiment_run,
    make_factor_candidate,
    make_model_candidate,
    make_strategy_candidate,
)


def test_all_research_outputs_carry_complete_lineage(fixed_start) -> None:
    lineage = {
        "code_sha": "a" * 40,
        "dataset_hash": "sha256:" + "b" * 64,
        "config_hash": "sha256:" + "c" * 64,
        "dependencies": {"pyqlib": "0.9.7", "rdagent": "0.8.0", "mlflow": "3.8.1"},
        "llm_metadata": {"provider": "azure-openai", "model": "research-model", "seed": 7},
        "artifacts": ["artifact://report.json"],
        "metrics": {"rank_ic": 0.04},
    }
    objects = [
        make_factor_candidate(fixed_start, **lineage),
        make_model_candidate(fixed_start, **lineage),
        make_strategy_candidate(fixed_start, **lineage),
        make_experiment_run(fixed_start, **lineage),
    ]

    for candidate in objects:
        assert candidate.code_sha == "a" * 40
        assert candidate.config_hash.startswith("sha256:")
        assert candidate.dependencies["rdagent"] == "0.8.0"
        assert candidate.llm_metadata["seed"] == 7
        assert candidate.artifacts == ["artifact://report.json"]
