"""Persistent storage for calibration artifacts and evaluation reports.

Layout under ``base_dir``::

    artifacts/<calibration_version>.json    one file per calibration
    evaluations/<report_id>.json            one file per evaluation report
    index.json                              latest artifact versions

Writes are atomic (temp file + ``os.replace``). MLflow experiment tracking is
optional and only attempted when the ``mlflow`` package is importable — the
store never depends on it. Tests exercise the JSON store; the API is the same
whether or not MLflow is present.
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from typing import Any
from uuid import UUID

from engines.signal_fusion.calibration import CalibrationArtifact
from engines.signal_fusion.evaluation import EvaluationReport

__all__ = ["CalibrationStore"]


class CalibrationStore:
    """Versioned, atomic JSON store for fusion calibration artifacts and metrics."""

    def __init__(
        self,
        base_dir: str | Path = "storage/calibration/signal_fusion",
        *,
        enable_mlflow: bool = False,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.enable_mlflow = enable_mlflow

    @property
    def artifacts_dir(self) -> Path:
        return self.base_dir / "artifacts"

    @property
    def evaluations_dir(self) -> Path:
        return self.base_dir / "evaluations"

    @property
    def index_path(self) -> Path:
        return self.base_dir / "index.json"

    # -- atomic IO -----------------------------------------------------------

    @staticmethod
    def _atomic_write(path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(text, encoding="utf-8")
        os.replace(tmp_path, path)

    def _read_json(self, path: Path) -> dict[str, Any]:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"{path} must contain a JSON object")
        return raw

    # -- artifacts -----------------------------------------------------------

    def save_artifact(self, artifact: CalibrationArtifact) -> Path:
        """Persist one calibration artifact (idempotent per version)."""
        path = self.artifacts_dir / f"{artifact.calibration_version}.json"
        self._atomic_write(path, artifact.model_dump_json(indent=2))
        self._update_index(artifact)
        self._log_artifact_mlflow(artifact)
        return path

    def load_artifact(self, calibration_version: str) -> CalibrationArtifact:
        path = self.artifacts_dir / f"{calibration_version}.json"
        if not path.is_file():
            raise FileNotFoundError(f"no calibration artifact for version {calibration_version!r}")
        return CalibrationArtifact.model_validate_json(path.read_text(encoding="utf-8"))

    def list_versions(self) -> list[str]:
        if not self.artifacts_dir.is_dir():
            return []
        return sorted(path.stem for path in self.artifacts_dir.glob("*.json"))

    def latest_artifact(self) -> CalibrationArtifact | None:
        versions = self.list_versions()
        if not versions:
            return None
        return max(
            (self.load_artifact(version) for version in versions),
            key=lambda artifact: artifact.trained_at,
        )

    def _update_index(self, artifact: CalibrationArtifact) -> None:
        index: dict[str, Any] = {}
        if self.index_path.is_file():
            index = self._read_json(self.index_path)
        index.setdefault("artifacts", {})[artifact.calibration_version] = {
            "artifact_id": str(artifact.artifact_id),
            "config_name": artifact.config.name,
            "trained_at": artifact.trained_at.isoformat(),
            "llm_added_value": artifact.llm_added_value,
            "llm_weight_bp": artifact.llm_weight_bp,
        }
        self._atomic_write(self.index_path, json.dumps(index, indent=2, sort_keys=True))

    # -- evaluations -----------------------------------------------------------

    def save_evaluation(self, report: EvaluationReport) -> Path:
        path = self.evaluations_dir / f"{report.report_id}.json"
        self._atomic_write(path, report.model_dump_json(indent=2))
        return path

    def load_evaluation(self, report_id: str | UUID) -> EvaluationReport:
        path = self.evaluations_dir / f"{report_id}.json"
        if not path.is_file():
            raise FileNotFoundError(f"no evaluation report with id {report_id!r}")
        return EvaluationReport.model_validate_json(path.read_text(encoding="utf-8"))

    # -- optional MLflow mirror ------------------------------------------------

    def _log_artifact_mlflow(self, artifact: CalibrationArtifact) -> None:
        if not self.enable_mlflow:
            return
        try:
            mlflow = importlib.import_module("mlflow")
        except ImportError:
            return
        try:
            mlflow.log_params(
                {
                    "calibration_version": artifact.calibration_version,
                    "config_name": artifact.config.name,
                    "llm_added_value": artifact.llm_added_value,
                    "llm_weight_bp": artifact.llm_weight_bp,
                }
            )
            for metric in artifact.train_metrics:
                if metric.mean_return is not None:
                    mlflow.log_metric(f"train.mean_return.{metric.config_name}", metric.mean_return)
                if metric.directional_accuracy is not None:
                    mlflow.log_metric(
                        f"train.accuracy.{metric.config_name}", metric.directional_accuracy
                    )
        except Exception:
            # MLflow must never break calibration persistence (INV-10: the JSON
            # store is the source of truth; MLflow is a mirror).
            return
