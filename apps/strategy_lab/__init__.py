"""Strategy Lab: offline, deterministic self-improvement (INV-8)."""

from apps.strategy_lab.evaluator import ReplayResult, replay
from apps.strategy_lab.lab import CandidateEval, ScalpingGrid, evaluate_grid, run_lab

__all__ = ["CandidateEval", "ReplayResult", "ScalpingGrid", "evaluate_grid", "replay", "run_lab"]
