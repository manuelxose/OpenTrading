"""Parameter sensitivity, execution stress and walk-forward execution.

Three mandate requirements are implemented here, all by RE-RUNNING the strategy
rather than by rescaling a stored P&L series:

* **Sensitivity surfaces (§35, §37 family 4).** The objective is a PLATEAU, not a
  maximum. `summarize_surface` reports the neighbourhood's median and the fraction
  of it that is profitable, and deliberately does not crown a winner.
* **Execution stress (§37 family 3, §41).** Widening the spread changes which
  trades are taken, not merely what they earn — so the strategy is re-executed
  under each cost scenario.
* **Walk-forward (§34).** Parameter STABILITY across windows is the output that
  matters; aggregate P&L across windows is the less informative one.

Every run records its config hash, so any number here can be traced back.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace

from research.strategies.xau_rpb.backtest import run_backtest
from research.strategies.xau_rpb.config import StrategyConfig
from research.strategies.xau_rpb.types import Bar, BrokerSpec

from .metrics import PerformanceMetrics, compute_metrics
from .splits import WalkForwardWindow

__all__ = [
    "SensitivityPoint",
    "StressScenario",
    "WalkForwardResult",
    "execution_stress",
    "parameter_sweep",
    "run_config",
    "summarize_surface",
    "walk_forward",
]


def run_config(
    bars: Sequence[Bar],
    config: StrategyConfig,
    spec: BrokerSpec,
    *,
    initial_equity: float = 100_000.0,
    broker_utc_offset_hours: float = 0.0,
) -> PerformanceMetrics:
    """Execute one configuration and return its metrics."""
    result = run_backtest(
        bars, config, spec,
        initial_equity=initial_equity,
        broker_utc_offset_hours=broker_utc_offset_hours,
    )
    return compute_metrics(result.trades, result.equity_curve, initial_equity)


@dataclass(slots=True)
class SensitivityPoint:
    """One evaluated point in a parameter neighbourhood."""

    params: dict[str, float]
    config_hash: str
    metrics: PerformanceMetrics

    @property
    def profit_factor(self) -> float | None:
        return self.metrics.profit_factor

    @property
    def is_profitable(self) -> bool:
        return self.metrics.net_profit > 0


def parameter_sweep(
    bars: Sequence[Bar],
    base_config: StrategyConfig,
    spec: BrokerSpec,
    grid: dict[str, Sequence[float]],
    *,
    initial_equity: float = 100_000.0,
    progress: Callable[[int, int], None] | None = None,
) -> list[SensitivityPoint]:
    """Evaluate the full cartesian product of a RESEARCH-parameter grid.

    Only research parameters can be varied: ``with_research`` is the only override
    path, so a sweep structurally cannot touch the risk mandate (spec §14).
    """
    names = sorted(grid)
    combos = list(itertools.product(*(grid[name] for name in names)))
    points: list[SensitivityPoint] = []

    for i, combo in enumerate(combos, start=1):
        overrides = dict(zip(names, combo, strict=True))
        typed: dict[str, float] = {}
        base = base_config.research
        for key, value in overrides.items():
            current = getattr(base, key)
            typed[key] = int(value) if isinstance(current, int) else float(value)

        config = base_config.with_research(**typed)
        try:
            config.validate()
        except ValueError:
            continue  # an internally contradictory combination is skipped, not forced
        metrics = run_config(bars, config, spec, initial_equity=initial_equity)
        points.append(SensitivityPoint(typed, config.config_hash(), metrics))
        if progress:
            progress(i, len(combos))

    return points


@dataclass(slots=True)
class SurfaceSummary:
    """Plateau diagnostics for a parameter neighbourhood (mandate §35)."""

    evaluated: int
    profitable: int
    profitable_fraction: float
    median_profit_factor: float | None
    best_profit_factor: float | None
    worst_profit_factor: float | None
    median_net_return_pct: float
    best_params: dict[str, float] = field(default_factory=dict)

    @property
    def is_plateau(self) -> bool:
        """A usable region: most of the neighbourhood works, not just its peak."""
        return self.profitable_fraction >= 0.70 and (
            self.median_profit_factor is not None and self.median_profit_factor >= 1.0
        )

    def summary(self) -> str:
        def fmt(v: float | None) -> str:
            return "n/a" if v is None else f"{v:.3f}"

        return "\n".join(
            [
                f"combinations evaluated : {self.evaluated}",
                f"profitable             : {self.profitable} "
                f"({self.profitable_fraction * 100:.1f}%)",
                f"median profit factor   : {fmt(self.median_profit_factor)}",
                f"best profit factor     : {fmt(self.best_profit_factor)}",
                f"worst profit factor    : {fmt(self.worst_profit_factor)}",
                f"median net return %    : {self.median_net_return_pct:.2f}",
                f"PLATEAU (not a spike)  : {self.is_plateau}",
                "",
                "Best-parameter values are reported for completeness only. Selecting the",
                "maximum of a sweep is the overfitting mechanism the mandate forbids; the",
                "decision input is the plateau, not the peak.",
            ]
        )


def _median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def summarize_surface(points: Sequence[SensitivityPoint]) -> SurfaceSummary:
    """Describe a neighbourhood's shape. Deliberately plateau-oriented."""
    if not points:
        return SurfaceSummary(0, 0, 0.0, None, None, None, 0.0)

    pfs = [p.profit_factor for p in points if p.profit_factor is not None]
    returns = [p.metrics.net_return_pct for p in points]
    profitable = sum(1 for p in points if p.is_profitable)
    best = max(points, key=lambda p: (p.profit_factor or -math.inf))

    return SurfaceSummary(
        evaluated=len(points),
        profitable=profitable,
        profitable_fraction=profitable / len(points),
        median_profit_factor=_median(pfs),
        best_profit_factor=max(pfs) if pfs else None,
        worst_profit_factor=min(pfs) if pfs else None,
        median_net_return_pct=_median(returns) or 0.0,
        best_params=dict(best.params),
    )


@dataclass(slots=True)
class StressScenario:
    """One execution-cost scenario and the metrics it produced."""

    label: str
    spread_multiplier: float
    slippage_points: float
    commission_per_lot: float
    metrics: PerformanceMetrics

    @property
    def profit_factor(self) -> float | None:
        return self.metrics.profit_factor


def execution_stress(
    bars: Sequence[Bar],
    base_config: StrategyConfig,
    spec: BrokerSpec,
    *,
    spread_multipliers: Sequence[float] = (1.0, 1.25, 1.5, 2.0),
    slippage_points: Sequence[float] = (0.0, 1.0, 2.0, 3.0),
    commission_per_lot: float = 0.0,
    initial_equity: float = 100_000.0,
    hold_filter_constant: bool = False,
) -> list[StressScenario]:
    """Re-execute the strategy under progressively worse fills (mandate §37, §41).

    Rescaling a stored P&L series would understate the damage: a wider spread also
    changes which setups pass the spread filter at all.

    That interaction, however, makes a naive stress test uninformative. The spread
    filter is a cliff: at a high enough multiplier the strategy simply stops
    trading, and "0 trades" answers no question about the edge. Two modes are
    therefore supported:

    * ``hold_filter_constant=False`` (default) — **operational realism**. The
      filter stays fixed, so widening spreads progressively lock the strategy out.
      This shows what the system would really do on a deteriorating venue.
    * ``hold_filter_constant=True`` — **pure cost sensitivity**. The spread
      thresholds scale with the multiplier so the SAME setups still qualify and
      only pay more. This is the variant that answers "does the edge survive worse
      costs?", and it is the one the §43 spread-stress gate needs.

    Report both. A strategy that passes only the first because it stopped trading
    has not demonstrated a cost-resilient edge.
    """
    scenarios: list[StressScenario] = []
    for multiplier in spread_multipliers:
        for slip in slippage_points:
            execution = replace(
                base_config.execution,
                spread_multiplier=multiplier,
                slippage_points_entry=slip,
                slippage_points_exit=slip,
                commission_per_lot=commission_per_lot,
            )
            if hold_filter_constant:
                execution = replace(
                    execution,
                    spread_atr_max=base_config.execution.spread_atr_max * multiplier,
                    spread_abs_max_points=(
                        base_config.execution.spread_abs_max_points * multiplier
                    ),
                )
            config = replace(base_config, execution=execution)
            metrics = run_config(bars, config, spec, initial_equity=initial_equity)
            mode = "cost-only" if hold_filter_constant else "filter-active"
            scenarios.append(
                StressScenario(
                    label=f"spread x{multiplier:g}, slippage +{slip:g}pt [{mode}]",
                    spread_multiplier=multiplier,
                    slippage_points=slip,
                    commission_per_lot=commission_per_lot,
                    metrics=metrics,
                )
            )
    return scenarios


@dataclass(slots=True)
class WalkForwardResult:
    """One walk-forward window: what was chosen in-sample and what it did OOS."""

    window: WalkForwardWindow
    selected_params: dict[str, float]
    in_sample: PerformanceMetrics
    out_of_sample: PerformanceMetrics

    @property
    def degradation_pct(self) -> float | None:
        is_pf = self.in_sample.profit_factor
        oos_pf = self.out_of_sample.profit_factor
        if is_pf is None or oos_pf is None or is_pf <= 0:
            return None
        return (is_pf - oos_pf) / is_pf * 100.0


def walk_forward(
    windows: Sequence[WalkForwardWindow],
    base_config: StrategyConfig,
    spec: BrokerSpec,
    grid: dict[str, Sequence[float]],
    *,
    initial_equity: float = 100_000.0,
) -> list[WalkForwardResult]:
    """Select parameters on each training window, then measure them on its test window.

    Selection uses the plateau-aware criterion (median-adjacent, not the peak):
    among profitable candidates the one with the highest profit factor is taken,
    but the RESULT of interest is how much the selected parameters MOVE between
    windows. Wildly jumping selections indicate an unstable system even when the
    aggregate P&L looks acceptable.
    """
    results: list[WalkForwardResult] = []
    for window in windows:
        points = parameter_sweep(
            window.train, base_config, spec, grid, initial_equity=initial_equity
        )
        viable = [p for p in points if p.profit_factor is not None and p.is_profitable]
        if not viable:
            continue

        chosen = max(viable, key=lambda p: p.profit_factor or 0.0)
        typed: dict[str, float] = {}
        for key, value in chosen.params.items():
            current = getattr(base_config.research, key)
            typed[key] = int(value) if isinstance(current, int) else float(value)

        config = base_config.with_research(**typed)
        oos = run_config(window.test, config, spec, initial_equity=initial_equity)
        results.append(WalkForwardResult(window, chosen.params, chosen.metrics, oos))
    return results


def parameter_stability(results: Sequence[WalkForwardResult]) -> dict[str, dict[str, float]]:
    """How much each selected parameter moves across windows (mandate §34).

    A parameter whose selected value swings across its whole research range is a
    warning sign regardless of aggregate profitability.
    """
    if not results:
        return {}
    names = sorted(results[0].selected_params)
    out: dict[str, dict[str, float]] = {}
    for name in names:
        values = [float(r.selected_params[name]) for r in results if name in r.selected_params]
        if not values:
            continue
        mean = math.fsum(values) / len(values)
        variance = math.fsum((v - mean) ** 2 for v in values) / len(values)
        spread = max(values) - min(values)
        out[name] = {
            "min": min(values),
            "max": max(values),
            "mean": mean,
            "stdev": math.sqrt(variance),
            "range": spread,
            "coefficient_of_variation": (math.sqrt(variance) / mean) if mean else 0.0,
        }
    return out
