"""Append-only canonical JSONL output store."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from core.schemas.base import DomainObject

from services.quant_rd.policy import ResearchAuthorityPolicy


class CandidateStore(Protocol):
    def append(self, value: DomainObject) -> str: ...


class JsonlCandidateStore:
    def __init__(self, output_root: Path, policy: ResearchAuthorityPolicy) -> None:
        self._root = policy.assert_writable_path(output_root)
        self._policy = policy

    def append(self, value: DomainObject) -> str:
        self._root.mkdir(parents=True, exist_ok=True)
        path = self._policy.assert_writable_path(self._root / f"{type(value).__name__}.jsonl")
        with path.open("a", encoding="utf-8") as stream:
            stream.write(value.to_json() + "\n")
        return path.as_uri()
