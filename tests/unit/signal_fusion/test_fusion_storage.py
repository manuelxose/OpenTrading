"""CalibrationStore: artifacts, metrics and index persist atomically."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from random import Random

import pytest
from core.domain.enums import SignalDirection
from core.schemas.fusion import FusionInputs
from engines.signal_fusion.calibration import calibrate
from engines.signal_fusion.evaluation import LabeledFusionCase, evaluate_cases
from engines.signal_fusion.storage import CalibrationStore

from factories import make_llm_signal, make_quant_signal

T0 = datetime(2026, 1, 5, 10, 0, 0, tzinfo=UTC)


def _cases(n: int = 40, seed: int = 1) -> list[LabeledFusionCase]:
    rng = Random(seed)
    cases: list[LabeledFusionCase] = []
    for i in range(n):
        t = T0 + timedelta(minutes=i)
        quant_dir = SignalDirection.LONG if rng.random() < 0.6 else SignalDirection.SHORT
        realized = 0.01 if quant_dir is SignalDirection.LONG else -0.01
        llm_dir = SignalDirection.LONG if rng.random() < 0.5 else SignalDirection.SHORT
        inputs = FusionInputs(
            quant=make_quant_signal(t, direction=quant_dir),
            llm=make_llm_signal(t, direction=llm_dir),
        )
        cases.append(LabeledFusionCase(inputs=inputs, realized_return=realized, as_of=t))
    return cases


class TestCalibrationStore:
    def test_artifact_roundtrip(self, tmp_path: Path) -> None:
        store = CalibrationStore(tmp_path)
        artifact = calibrate(_cases(), name="roundtrip", trained_at=T0, weight_step_bp=500)
        path = store.save_artifact(artifact)
        assert path.is_file()
        loaded = store.load_artifact(artifact.calibration_version)
        assert loaded.calibration_version == artifact.calibration_version
        assert loaded.config.model_dump_json() == artifact.config.model_dump_json()
        assert loaded.llm_added_value == artifact.llm_added_value
        assert loaded.train_metrics == artifact.train_metrics

    def test_save_is_idempotent_per_version(self, tmp_path: Path) -> None:
        store = CalibrationStore(tmp_path)
        artifact = calibrate(_cases(), name="idem", trained_at=T0, weight_step_bp=500)
        store.save_artifact(artifact)
        store.save_artifact(artifact)
        assert store.list_versions() == [artifact.calibration_version]

    def test_latest_artifact(self, tmp_path: Path) -> None:
        store = CalibrationStore(tmp_path)
        first = calibrate(_cases(seed=1), name="v1", trained_at=T0, weight_step_bp=500)
        second = calibrate(
            _cases(seed=2),
            name="v2",
            trained_at=T0 + timedelta(minutes=1),
            weight_step_bp=500,
        )
        store.save_artifact(first)
        store.save_artifact(second)
        latest = store.latest_artifact()
        assert latest is not None
        assert latest.calibration_version == second.calibration_version
        assert store.list_versions() == sorted(
            [first.calibration_version, second.calibration_version]
        )

    def test_index_records_versions(self, tmp_path: Path) -> None:
        store = CalibrationStore(tmp_path)
        artifact = calibrate(_cases(), name="indexed", trained_at=T0, weight_step_bp=500)
        store.save_artifact(artifact)
        assert store.index_path.is_file()
        assert artifact.calibration_version in store.index_path.read_text()

    def test_missing_version_raises(self, tmp_path: Path) -> None:
        store = CalibrationStore(tmp_path)
        with pytest.raises(FileNotFoundError):
            store.load_artifact("does-not-exist")

    def test_empty_store_has_no_latest(self, tmp_path: Path) -> None:
        store = CalibrationStore(tmp_path)
        assert store.latest_artifact() is None
        assert store.list_versions() == []

    def test_evaluation_roundtrip(self, tmp_path: Path) -> None:
        store = CalibrationStore(tmp_path)
        artifact = calibrate(_cases(), name="eval-store", trained_at=T0, weight_step_bp=500)
        report = evaluate_cases(_cases(seed=3), config=artifact.config, evaluated_at=T0)
        path = store.save_evaluation(report)
        assert path.is_file()
        loaded = store.load_evaluation(report.report_id)
        assert loaded.report_id == report.report_id
        assert loaded.winner == report.winner
        assert loaded.metrics == report.metrics

    def test_store_never_breaks_without_mlflow(self, tmp_path: Path) -> None:
        # MLflow is optional; storage must work identically without it.
        store = CalibrationStore(tmp_path, enable_mlflow=True)
        artifact = calibrate(_cases(), name="no-mlflow", trained_at=T0, weight_step_bp=500)
        assert store.save_artifact(artifact).is_file()
