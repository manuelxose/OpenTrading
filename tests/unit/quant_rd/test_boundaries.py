from __future__ import annotations

import ast
from pathlib import Path

from core.domain.enums import StrategyState
from services.quant_rd.bootstrap import validate_authority_environment
from services.quant_rd.policy import ResearchAuthorityPolicy, ResearchBoundaryViolation


def test_quant_rd_source_cannot_import_live_capital_modules() -> None:
    roots = [Path("adapters/qlib"), Path("adapters/rdagent"), Path("services/quant_rd")]
    forbidden = ("engines.risk", "engines.execution", "adapters.mt4", "mt4")
    violations: list[str] = []
    for root in roots:
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for name in names:
                    if name.startswith(forbidden):
                        violations.append(f"{path}:{name}")
    assert violations == []


def test_policy_rejects_live_states_and_forbidden_paths(tmp_path: Path) -> None:
    policy = ResearchAuthorityPolicy(tmp_path / "workspace", tmp_path / "outputs")
    policy.assert_strategy_state(StrategyState.CANDIDATE)

    for state in (StrategyState.PAPER, StrategyState.LIVE_GATED, StrategyState.LIVE_AUTO):
        try:
            policy.assert_strategy_state(state)
        except ResearchBoundaryViolation:
            pass
        else:
            raise AssertionError(f"research accepted forbidden state {state}")

    try:
        policy.assert_writable_path(tmp_path / "production" / "risk.py")
    except ResearchBoundaryViolation:
        pass
    else:
        raise AssertionError("research accepted a path outside its roots")


def test_bootstrap_fails_closed_for_live_or_broker_authority() -> None:
    validate_authority_environment({"OT_OPERATING_MODE": "RESEARCH"})
    forbidden = [
        {"OT_OPERATING_MODE": "LIVE_AUTO"},
        {"OT_BROKER_ENABLED": "true"},
        {"MT4_PASSWORD": "secret"},
        {"BROKER_ACCOUNT_ID": "123"},
    ]
    for environment in forbidden:
        try:
            validate_authority_environment(environment)
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"bootstrap accepted forbidden environment {environment}")
