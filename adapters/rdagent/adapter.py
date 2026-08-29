"""RD-Agent translation seam for the isolated Python 3.11 service."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from adapters.rdagent.schemas import Hypothesis, Implementation


class RDAgentBackend(Protocol):
    def generate_hypothesis(self, kind: str, context: Mapping[str, Any]) -> Mapping[str, Any]: ...

    def implement(self, hypothesis: Mapping[str, Any]) -> Mapping[str, Any]: ...


class RDAgentAdapter:
    """Validate untrusted upstream output before it enters a workflow."""

    def __init__(self, backend: RDAgentBackend) -> None:
        self._backend = backend

    def generate_hypothesis(self, kind: str, context: Mapping[str, Any]) -> Hypothesis:
        return Hypothesis.model_validate(self._backend.generate_hypothesis(kind, context))

    def implement(self, hypothesis: Hypothesis) -> Implementation:
        return Implementation.model_validate(self._backend.implement(hypothesis.model_dump()))
