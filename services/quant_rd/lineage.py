"""Deterministic experiment lineage utilities."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from importlib.metadata import PackageNotFoundError, version
from typing import Any

PINNED_DEPENDENCIES = {"rdagent": "0.8.0", "pyqlib": "0.9.7", "mlflow": "3.8.1"}


def content_hash(value: str | bytes) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def config_hash(config: Mapping[str, Any]) -> str:
    canonical = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return content_hash(canonical)


def installed_dependencies() -> dict[str, str]:
    """Fail when the isolated environment differs from its audited pins."""
    found: dict[str, str] = {}
    for package, expected in PINNED_DEPENDENCIES.items():
        try:
            actual = version(package)
        except PackageNotFoundError as exc:
            raise RuntimeError(f"required research dependency is missing: {package}") from exc
        if actual != expected:
            raise RuntimeError(f"{package} must be {expected}, found {actual}")
        found[package] = actual
    return found
