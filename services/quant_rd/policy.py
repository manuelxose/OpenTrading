"""Fail-closed authority and filesystem policy for autonomous research."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.domain.enums import StrategyState


class ResearchBoundaryViolation(PermissionError):
    """Raised when research attempts an action outside its authority."""


@dataclass(frozen=True)
class ResearchAuthorityPolicy:
    """The complete authority granted to the Quant R&D runtime."""

    workspace_root: Path
    output_root: Path

    def assert_strategy_state(self, state: StrategyState) -> None:
        if state not in {
            StrategyState.IDEA,
            StrategyState.CANDIDATE,
            StrategyState.BACKTESTED,
            StrategyState.WALK_FORWARD_OK,
            StrategyState.ROBUSTNESS_OK,
        }:
            raise ResearchBoundaryViolation(f"Quant R&D cannot create state {state.value}")

    def assert_writable_path(self, path: Path) -> Path:
        resolved = path.resolve()
        roots = (self.workspace_root.resolve(), self.output_root.resolve())
        if not any(resolved == root or root in resolved.parents for root in roots):
            raise ResearchBoundaryViolation(f"write outside research roots: {resolved}")
        return resolved
