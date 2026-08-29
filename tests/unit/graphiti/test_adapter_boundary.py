"""Boundary contract tests: Graphiti can disappear entirely.

These tests enforce the strict adapter boundary:

1. No module outside ``adapters/graphiti/`` imports upstream ``graphiti_core``.
2. Inside the adapter, only ``client.py`` may import upstream, and only inside
   its lazy import seam.
3. With the ``graphiti_core`` import blocked, the package still imports, the
   in-memory twin still drives the full memory path, and the live store fails
   safely with a typed error.
"""

from __future__ import annotations

import ast
import builtins
import importlib
from pathlib import Path

import pytest
from adapters.graphiti import InMemoryStore, Memory, client
from adapters.graphiti.errors import GraphitiIngestError, GraphitiUnavailableError

from factories import FIXED_START
from gt_test_helpers import make_record

REPO_ROOT = Path(__file__).resolve().parents[3]
SCAN_ROOTS = ["core", "engines", "apps", "adapters"]
ADAPTER_DIR = REPO_ROOT / "adapters" / "graphiti"

UPSTREAM_MODULE = "graphiti_core"


def _imports_in(path: Path) -> list[tuple[ast.AST, str]]:
    """(node, module-name) for every import in a file, with module context."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[ast.AST, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((node, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            found.append((node, node.module))
    return found


def _within_function(node: ast.AST, tree: ast.AST) -> bool:
    """Whether ``node`` sits inside a function definition (lazy import seam)."""
    lineno = getattr(node, "lineno", None)
    if lineno is None:
        return False
    for scope in ast.walk(tree):
        if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        end = getattr(scope, "end_lineno", scope.lineno)
        if scope.lineno <= lineno <= end and node is not scope:
            return True
    return False


def test_no_module_outside_adapter_imports_upstream() -> None:
    offenders: dict[str, list[str]] = {}
    for root in SCAN_ROOTS:
        root_path = REPO_ROOT / root
        if not root_path.exists():
            continue
        for path in root_path.rglob("*.py"):
            if ADAPTER_DIR in path.parents or path.parent == ADAPTER_DIR:
                continue  # the adapter itself is scanned separately below
            for _, module in _imports_in(path):
                if module == UPSTREAM_MODULE or module.startswith(UPSTREAM_MODULE + "."):
                    offenders.setdefault(str(path.relative_to(REPO_ROOT)), []).append(module)
    assert not offenders, f"only adapters/graphiti may import upstream: {offenders}"


def test_only_client_imports_upstream_and_only_lazily() -> None:
    for path in ADAPTER_DIR.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node, module in _imports_in(path):
            if not (module == UPSTREAM_MODULE or module.startswith(UPSTREAM_MODULE + ".")):
                continue
            assert path.name == "client.py", f"{path.name} imports upstream; only client.py may"
            assert _within_function(node, tree), (
                f"{path.name}:{node.lineno} imports upstream outside a function"
            )


class _UpstreamImportBlock:
    """Block any import of the ``graphiti_core`` top-level package."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._monkeypatch = monkeypatch
        self._original = builtins.__import__

    def __enter__(self) -> _UpstreamImportBlock:
        def blocked(name: str, *args: object, **kwargs: object) -> object:
            if name == UPSTREAM_MODULE or name.startswith(UPSTREAM_MODULE + "."):
                raise ImportError(f"blocked import of {name!r}")
            return self._original(name, *args, **kwargs)  # type: ignore[no-any-return]

        self._monkeypatch.setattr(builtins, "__import__", blocked)
        return self

    def __exit__(self, *exc: object) -> None:
        self._monkeypatch.undo()


def test_graphiti_can_disappear_and_the_domain_still_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _UpstreamImportBlock(monkeypatch):
        # 1. The package itself imports cleanly without upstream present.
        importlib.reload(importlib.import_module("adapters.graphiti"))

        # 2. The in-memory twin drives the full memory path.
        record = make_record(FIXED_START, summary="postmortem lesson")
        memory = Memory(InMemoryStore([record]))
        results = memory.search("postmortem", as_of=FIXED_START)
        assert [r.summary for r in results] == ["postmortem lesson"]

        # 3. The live store fails safely with a typed adapter error — never a
        #    raw ImportError escaping the boundary.
        live = client.LiveGraphitiStore(check_version=False)
        with pytest.raises(GraphitiIngestError):
            live.store(record)


def test_live_store_never_leaks_upstream_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("adapters.graphiti.client._installed_version", lambda: None)
    # pytest.raises fails the test if a raw ImportError escapes instead.
    with _UpstreamImportBlock(monkeypatch), pytest.raises(GraphitiUnavailableError):
        client.LiveGraphitiStore()
