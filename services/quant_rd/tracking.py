"""MLflow integration behind a canonical-record interface."""

from __future__ import annotations

from typing import Any, Protocol

from core.schemas.research_factory import ExperimentRun


class ExperimentTracker(Protocol):
    def log(self, run: ExperimentRun) -> None: ...


class MlflowExperimentTracker:
    """Log complete canonical experiment records using MLflow 3.8.1."""

    def __init__(self, tracking_uri: str, experiment_name: str = "quant-rd") -> None:
        import mlflow  # type: ignore[import-not-found]

        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(experiment_name)
        self._mlflow: Any = mlflow

    def log(self, run: ExperimentRun) -> None:
        with self._mlflow.start_run(run_name=run.name, run_id=None):
            self._mlflow.log_params(
                {
                    "canonical_experiment_id": str(run.experiment_id),
                    "code_sha": run.code_sha or "",
                    "dataset_hash": run.dataset_hash or "",
                    "config_hash": run.config_hash or "",
                    "seed": run.seed if run.seed is not None else "",
                    **{f"dependency.{key}": value for key, value in run.dependencies.items()},
                }
            )
            self._mlflow.log_metrics(run.metrics)
            self._mlflow.set_tags(
                {f"llm.{key}": str(value) for key, value in run.llm_metadata.items()}
            )
            self._mlflow.log_dict(run.canonical_dict(), "canonical/ExperimentRun.json")
