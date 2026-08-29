"""Quant factory contracts: factor/model/strategy candidates and experiment runs
(RD-Agent + Qlib, Phase 9+; INV-8, INV-14)."""

from __future__ import annotations

from typing import Any, Self
from uuid import UUID

from pydantic import Field, model_validator

from core.domain.enums import CandidateStatus, ExperimentStatus, StrategyState
from core.schemas.base import DomainObject, UtcDateTime

__all__ = ["ExperimentRun", "FactorCandidate", "ModelCandidate", "StrategyCandidate"]


class FactorCandidate(DomainObject):
    """A proposed alpha factor produced by the R&D factory."""

    candidate_id: UUID
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    expression: str | None = None
    input_features: list[str] = Field(default_factory=list)
    horizon: str | None = None
    status: CandidateStatus = CandidateStatus.PROPOSED
    generated_by_run: str | None = None
    ic: float | None = Field(default=None, description="Information coefficient")
    rank_ic: float | None = None
    code_sha: str | None = None
    dataset_hash: str | None = None
    config_hash: str | None = None
    metrics: dict[str, float] = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)
    dependencies: dict[str, str] = Field(default_factory=dict)
    llm_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_quant_rd_lineage(self) -> Self:
        if self.provenance.producer == "quant-rd" and self.status is CandidateStatus.VALIDATED:
            _validate_lineage(self, require_metrics=True)
        return self


class ModelCandidate(DomainObject):
    """A trained model candidate with reproducible training metadata."""

    candidate_id: UUID
    name: str = Field(min_length=1)
    model_type: str = Field(min_length=1)
    framework: str = Field(min_length=1)
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    features: list[str] = Field(default_factory=list)
    training_dataset_ref: str = Field(min_length=1)
    dataset_hash: str | None = None
    code_ref: str | None = None
    code_sha: str | None = None
    seed: int | None = None
    metrics: dict[str, float] = Field(default_factory=dict)
    status: CandidateStatus = CandidateStatus.PROPOSED
    produced_by_run: str | None = None
    config_hash: str | None = None
    artifacts: list[str] = Field(default_factory=list)
    dependencies: dict[str, str] = Field(default_factory=dict)
    llm_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_quant_rd_lineage(self) -> Self:
        if self.provenance.producer == "quant-rd" and self.status is CandidateStatus.VALIDATED:
            _validate_lineage(self, require_metrics=True)
            if self.seed is None:
                raise ValueError("quant-rd ModelCandidate requires seed")
        return self


class StrategyCandidate(DomainObject):
    """A strategy under the INV-8 lifecycle. No RD-Agent -> LIVE edge exists."""

    candidate_id: UUID
    name: str = Field(min_length=1)
    state: StrategyState = StrategyState.CANDIDATE
    factor_ids: list[str] = Field(default_factory=list)
    model_ids: list[str] = Field(default_factory=list)
    entry_rules: str | None = None
    exit_rules: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    code_sha: str | None = None
    data_hash: str | None = None
    dataset_hash: str | None = None
    metrics: dict[str, float] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    originated_from: str | None = None
    config_hash: str | None = None
    dependencies: dict[str, str] = Field(default_factory=dict)
    llm_metadata: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_quant_rd_lineage(self) -> Self:
        if self.provenance.producer == "quant-rd":
            _validate_lineage(self, require_metrics=True)
        return self


class ExperimentRun(DomainObject):
    """One reproducible experiment (MLflow-native abstraction, architecture §10)."""

    experiment_id: UUID
    name: str = Field(min_length=1)
    experiment_type: str = Field(min_length=1, description="FACTOR | MODEL | STRATEGY | BASELINE")
    config: dict[str, Any] = Field(default_factory=dict)
    dataset_ref: str = Field(min_length=1)
    dataset_hash: str | None = None
    code_sha: str | None = None
    config_hash: str | None = None
    seed: int | None = None
    environment_pin: dict[str, str] = Field(default_factory=dict)
    status: ExperimentStatus = ExperimentStatus.RUNNING
    started_at: UtcDateTime
    finished_at: UtcDateTime | None = None
    results: dict[str, Any] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)
    dependencies: dict[str, str] = Field(default_factory=dict)
    llm_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_status(self) -> Self:
        if self.status is ExperimentStatus.RUNNING:
            if self.finished_at is not None:
                raise ValueError("a RUNNING experiment must not have finished_at")
        elif self.finished_at is None:
            raise ValueError(f"experiment status {self.status.value} requires finished_at")
        if self.provenance.producer == "quant-rd" and self.status is not ExperimentStatus.RUNNING:
            _validate_lineage(self, require_metrics=self.status is ExperimentStatus.COMPLETED)
            if self.seed is None:
                raise ValueError("quant-rd ExperimentRun requires seed")
        return self


def _validate_lineage(value: Any, *, require_metrics: bool) -> None:
    for field in ("code_sha", "dataset_hash", "config_hash"):
        if not getattr(value, field, None):
            raise ValueError(f"quant-rd output requires {field}")
    if not value.dependencies:
        raise ValueError("quant-rd output requires dependencies")
    if not value.llm_metadata:
        raise ValueError("quant-rd output requires llm_metadata")
    if not value.artifacts:
        raise ValueError("quant-rd output requires artifacts")
    if require_metrics and not value.metrics:
        raise ValueError("successful quant-rd output requires metrics")
