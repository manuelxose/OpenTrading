"""Boundary contract tests: TradingAgents can disappear entirely.

These tests enforce the strict adapter boundary:

1. No module outside ``adapters/tradingagents/`` imports upstream.
2. Inside the adapter, only ``client.py`` may import upstream, and only inside
   its lazy import seam.
3. The adapter never imports execution machinery (MT4, OrderIntent).
4. With the ``tradingagents`` import blocked, the package still imports, the
   mock adapter still drives the full domain path, and the live adapter fails
   safely with a typed error.
"""

from __future__ import annotations

import ast
import builtins
import importlib
from pathlib import Path

import pytest
from adapters.tradingagents import MockTradingAgentsAdapter, client
from adapters.tradingagents.errors import TradingAgentsUnavailableError
from adapters.tradingagents.schemas import AdapterConfig
from core.domain.enums import SignalDirection
from core.schemas.signals import CommitteeMember, LLMSignal
from ta_test_helpers import build_research_request

from factories import FIXED_START, make_market_snapshot

REPO_ROOT = Path(__file__).resolve().parents[3]
SCAN_ROOTS = ["core", "engines", "apps", "adapters"]
ADAPTER_DIR = REPO_ROOT / "adapters" / "tradingagents"

UPSTREAM_MODULE = "tradingagents"
EXECUTION_MODULES = {
    "adapters.mt4",
    "mt4",
    "MetaTrader5",
    "mt5",
    "core.schemas.trading",
    "core.schemas.execution",
}


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
    assert not offenders, f"only adapters/tradingagents may import upstream: {offenders}"


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


def test_adapter_never_imports_execution_machinery() -> None:
    offenders: dict[str, list[str]] = {}
    for path in ADAPTER_DIR.rglob("*.py"):
        for _, module in _imports_in(path):
            if module in EXECUTION_MODULES:
                offenders.setdefault(path.name, []).append(module)
    assert not offenders, f"adapter must never import execution machinery: {offenders}"


def test_llmsignal_schema_has_no_execution_capability() -> None:
    execution_vocabulary = {
        "order",
        "intent",
        "quantity",
        "sizing",
        "stop",
        "lot",
        "position",
        "entry_price",
        "limit",
        "fill",
    }
    assert not (set(LLMSignal.model_fields) & execution_vocabulary)
    assert not (set(CommitteeMember.model_fields) & execution_vocabulary)


class _UpstreamImportBlock:
    """Block any import of the ``tradingagents`` top-level package."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._monkeypatch = monkeypatch
        self._original = builtins.__import__

    def __enter__(self) -> _UpstreamImportBlock:
        def blocked(name: str, *args: object, **kwargs: object) -> object:
            if name == "tradingagents" or name.startswith("tradingagents."):
                raise ImportError(f"blocked import of {name!r}")
            return self._original(name, *args, **kwargs)  # type: ignore[no-any-return]

        self._monkeypatch.setattr(builtins, "__import__", blocked)
        return self

    def __exit__(self, *exc: object) -> None:
        self._monkeypatch.undo()


def test_tradingagents_can_disappear_and_the_domain_still_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _UpstreamImportBlock(monkeypatch):
        # 1. The package itself imports cleanly without upstream present.
        importlib.reload(importlib.import_module("adapters.tradingagents"))

        # 2. The mock adapter drives the full domain path.
        adapter = MockTradingAgentsAdapter()
        request = build_research_request(FIXED_START)
        signal = adapter.run(
            request,
            make_market_snapshot(FIXED_START, instrument_id="NVDA"),
            now=FIXED_START,
        )
        assert isinstance(signal, LLMSignal)
        assert signal.direction is SignalDirection.FLAT

        # 3. The live adapter fails safely with a typed adapter error — never a
        #    raw ImportError escaping the boundary.
        live = client.LiveTradingAgentsAdapter(
            AdapterConfig(llm_provider="openai", deep_think_llm="gpt-x", quick_think_llm="gpt-y")
        )
        with pytest.raises(TradingAgentsUnavailableError):
            live.run(
                request,
                make_market_snapshot(FIXED_START, instrument_id="NVDA"),
                now=FIXED_START,
            )


def test_live_adapter_failure_is_never_a_raw_importerror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    live = client.LiveTradingAgentsAdapter(
        AdapterConfig(llm_provider="openai", deep_think_llm="gpt-x", quick_think_llm="gpt-y")
    )
    # pytest.raises fails the test if a raw ImportError escapes instead.
    with _UpstreamImportBlock(monkeypatch), pytest.raises(TradingAgentsUnavailableError):
        live.run(
            build_research_request(FIXED_START),
            make_market_snapshot(FIXED_START, instrument_id="NVDA"),
            now=FIXED_START,
        )
