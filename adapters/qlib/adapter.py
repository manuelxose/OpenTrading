"""Qlib result mapper; Qlib classes never enter the canonical domain."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class EvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    metrics: dict[str, float] = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class QlibBackend(Protocol):
    def test_factor(self, code: str, config: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def test_model(self, code: str, config: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def evaluate_strategy(self, config: Mapping[str, Any]) -> Mapping[str, Any]: ...


class QlibAdapter:
    def __init__(self, backend: QlibBackend) -> None:
        self._backend = backend

    def test_factor(self, code: str, config: Mapping[str, Any]) -> EvaluationResult:
        return EvaluationResult.model_validate(self._backend.test_factor(code, config))

    def test_model(self, code: str, config: Mapping[str, Any]) -> EvaluationResult:
        return EvaluationResult.model_validate(self._backend.test_model(code, config))

    def evaluate_strategy(self, config: Mapping[str, Any]) -> EvaluationResult:
        return EvaluationResult.model_validate(self._backend.evaluate_strategy(config))
