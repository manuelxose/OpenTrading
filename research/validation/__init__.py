"""Validation, robustness and anti-overfitting tooling for XAU_RPB.

Implements mandate §33-§44: chronological splits, walk-forward, Monte Carlo,
parameter sensitivity, execution stress, PBO/CSCV, Deflated Sharpe, and the frozen
acceptance gates.

The tooling is complete and executable. Whether it has ever been RUN on real
market data is a separate question, answered honestly in
``docs/strategy/RESEARCH_REPORT.md``.
"""

from __future__ import annotations

from .gates import GateOutcome, GateReport, GateResult, Qualification, evaluate_gates
from .metrics import (
    PerformanceMetrics,
    compute_metrics,
    group_by,
    max_drawdown,
    side_breakdown,
    yearly_breakdown,
)
from .monte_carlo import MonteCarloResult, block_bootstrap, percentile, sequence_bootstrap
from .overfitting import (
    TrialLedger,
    deflated_sharpe_ratio,
    expected_max_sharpe,
    probability_of_backtest_overfitting,
)
from .splits import (
    OosLedger,
    Partition,
    Split,
    WalkForwardWindow,
    chronological_split,
    walk_forward_windows,
)
from .sweeps import (
    SensitivityPoint,
    StressScenario,
    WalkForwardResult,
    execution_stress,
    parameter_stability,
    parameter_sweep,
    run_config,
    summarize_surface,
    walk_forward,
)

__all__ = [
    "GateOutcome",
    "GateReport",
    "GateResult",
    "MonteCarloResult",
    "OosLedger",
    "Partition",
    "PerformanceMetrics",
    "Qualification",
    "SensitivityPoint",
    "Split",
    "StressScenario",
    "TrialLedger",
    "WalkForwardResult",
    "WalkForwardWindow",
    "block_bootstrap",
    "chronological_split",
    "compute_metrics",
    "deflated_sharpe_ratio",
    "evaluate_gates",
    "execution_stress",
    "expected_max_sharpe",
    "group_by",
    "max_drawdown",
    "parameter_stability",
    "parameter_sweep",
    "percentile",
    "probability_of_backtest_overfitting",
    "run_config",
    "sequence_bootstrap",
    "side_breakdown",
    "summarize_surface",
    "walk_forward",
    "walk_forward_windows",
    "yearly_breakdown",
]
