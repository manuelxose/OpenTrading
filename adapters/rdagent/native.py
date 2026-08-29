"""Concrete bridge to RD-Agent 0.8.0's Qlib factor/model loops.

All imports of upstream classes are confined to this adapter module.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class NativeRDAgentQlibBackend:
    """Drive one official RD-Agent hypothesis/code/run cycle at a time."""

    def __init__(self) -> None:
        from rdagent.app.qlib_rd_loop.conf import (  # type: ignore[import-not-found]
            FACTOR_PROP_SETTING,
            MODEL_PROP_SETTING,
        )
        from rdagent.app.qlib_rd_loop.factor import FactorRDLoop  # type: ignore[import-not-found]
        from rdagent.app.qlib_rd_loop.model import ModelRDLoop  # type: ignore[import-not-found]

        self._loop_factories = {
            "factor": lambda: FactorRDLoop(FACTOR_PROP_SETTING),
            "model": lambda: ModelRDLoop(MODEL_PROP_SETTING),
        }
        self._state: dict[str, Any] = {}
        self._last_results: dict[str, dict[str, Any]] = {}

    def generate_hypothesis(self, kind: str, context: Mapping[str, Any]) -> Mapping[str, Any]:
        if kind not in self._loop_factories:
            raise ValueError(f"unsupported RD-Agent hypothesis kind: {kind}")
        loop = self._loop_factories[kind]()
        raw = loop._propose()
        self._state[kind] = {"loop": loop, "hypothesis": raw}
        return {
            "kind": kind,
            "title": str(raw.hypothesis),
            "rationale": str(raw.reason),
            "metadata": {"context": dict(context)},
        }

    def implement(self, hypothesis: Mapping[str, Any]) -> Mapping[str, Any]:
        kind = str(hypothesis["kind"])
        state = self._state[kind]
        experiment = state["loop"]._exp_gen(state["hypothesis"])
        coding = state["loop"].coder.develop(experiment)
        state["coding"] = coding
        code, artifacts = self._collect_code(coding)
        state["artifacts"] = artifacts
        return {
            "kind": kind,
            "name": str(hypothesis["title"]),
            "code": code,
            "parameters": {},
            "llm_metadata": {
                "chat_model": os.environ.get("CHAT_MODEL", "unreported"),
                "embedding_model": os.environ.get("EMBEDDING_MODEL", "unreported"),
                "framework": "rdagent-0.8.0",
            },
        }

    def test_factor(self, code: str, config: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._run("factor")

    def test_model(self, code: str, config: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._run("model")

    def evaluate_strategy(self, config: Mapping[str, Any]) -> Mapping[str, Any]:
        metrics: dict[str, float] = {}
        artifacts: list[str] = []
        for result in self._last_results.values():
            metrics.update(result["metrics"])
            artifacts.extend(result["artifacts"])
        if not metrics:
            raise RuntimeError("RD-Agent/Qlib produced no numeric evaluation metrics")
        return {"metrics": metrics, "artifacts": artifacts, "details": {"config": dict(config)}}

    def _run(self, kind: str) -> Mapping[str, Any]:
        state = self._state[kind]
        result = state["loop"].runner.develop(state["coding"])
        metrics = self._numeric_metrics(result)
        if not metrics:
            raise RuntimeError(f"RD-Agent/Qlib {kind} run produced no numeric metrics")
        mapped = {
            "metrics": metrics,
            "artifacts": state.get("artifacts", []),
            "details": {"upstream_result_type": type(result).__name__},
        }
        self._last_results[kind] = mapped
        return mapped

    @staticmethod
    def _collect_code(value: Any) -> tuple[str, list[str]]:
        roots: list[Path] = []
        for workspace in getattr(value, "sub_workspace_list", [value]):
            for attribute in ("workspace_path", "path"):
                candidate = getattr(workspace, attribute, None)
                if candidate:
                    roots.append(Path(candidate))
        files = sorted({path for root in roots if root.exists() for path in root.rglob("*.py")})
        if not files:
            raise RuntimeError("RD-Agent implementation produced no Python source artifact")
        code = "\n\n".join(path.read_text(encoding="utf-8") for path in files)
        return code, [path.resolve().as_uri() for path in files]

    @classmethod
    def _numeric_metrics(cls, value: Any) -> dict[str, float]:
        metrics: dict[str, float] = {}
        candidates = [value, getattr(value, "result", None), getattr(value, "results", None)]
        for candidate in candidates:
            if isinstance(candidate, Mapping):
                for key, item in candidate.items():
                    if isinstance(item, int | float) and not isinstance(item, bool):
                        metrics[str(key)] = float(item)
        return metrics
