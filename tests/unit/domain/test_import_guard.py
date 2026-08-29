"""DoD guard: the domain layer (core/) imports no external trading framework.

Architecture §15 / Phase 0 DoD: the domain must not import TradingAgents, MT4, Qlib,
Graphiti or Nautilus directly.
"""

from __future__ import annotations

import ast
from pathlib import Path

CORE_DIR = Path(__file__).resolve().parents[3] / "core"

FORBIDDEN_TOP_LEVEL_MODULES = {
    "graphiti",
    "nautilus_trader",
    "nautilus",
    "qlib",
    "rdagent",
    "tradingagents",
    "MetaTrader5",
    "mt5",
    "zmq",
}


def _forbidden_imports(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".", 1)[0]
                if top in FORBIDDEN_TOP_LEVEL_MODULES:
                    found.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            top = node.module.split(".", 1)[0]
            if top in FORBIDDEN_TOP_LEVEL_MODULES:
                found.append(node.module)
    return found


def test_core_imports_no_external_trading_framework() -> None:
    offenders: dict[str, list[str]] = {}
    for path in sorted(CORE_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found = _forbidden_imports(tree)
        if found:
            offenders[str(path.relative_to(CORE_DIR))] = found
    assert not offenders, (
        f"core/ must not import external trading frameworks (Phase 0 DoD): {offenders}"
    )


def test_core_sources_exist() -> None:
    required = [
        "domain/enums.py",
        "domain/state_machines.py",
        "schemas/base.py",
        "events/registry.py",
        "config/settings.py",
        "clock/clocks.py",
        "audit/audit.py",
    ]
    for rel in required:
        assert (CORE_DIR / rel).is_file(), f"missing core module: {rel}"
