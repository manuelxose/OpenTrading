"""Acceptance gates and automatic rejection conditions (mandate §43, §44).

These thresholds are frozen deliberately. The single most valuable property of a
gate is that it was written down *before* the results were seen — a gate relaxed
after a disappointing run is not a gate, it is a rationalization.

`evaluate_gates` therefore takes no tuning arguments. If a future mandate changes
a threshold, that is a versioned edit to this file with a reason, reviewable in
the diff, not a runtime parameter.

A strategy that fails is a successful research outcome (mandate §67).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .metrics import PerformanceMetrics

__all__ = [
    "GateOutcome",
    "GateReport",
    "GateResult",
    "Qualification",
    "evaluate_gates",
]


class GateOutcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    DESIRED_MET = "PASS_DESIRED"
    NOT_EVALUABLE = "NOT_EVALUABLE"


class Qualification(StrEnum):
    """The only permitted final classifications (mandate §61 Phase 13)."""

    REJECTED = "REJECTED"
    RESEARCH_ONLY = "RESEARCH ONLY"
    FORWARD_TEST_CANDIDATE = "FORWARD-TEST CANDIDATE"
    MICRO_LIVE_CANDIDATE = "MICRO-LIVE CANDIDATE"


@dataclass(slots=True)
class GateResult:
    name: str
    outcome: GateOutcome
    observed: float | None
    minimum: float | None
    desired: float | None
    note: str = ""

    @property
    def failed(self) -> bool:
        return self.outcome is GateOutcome.FAIL


@dataclass(slots=True)
class GateReport:
    results: list[GateResult] = field(default_factory=list)
    rejections: list[str] = field(default_factory=list)
    qualification: Qualification = Qualification.RESEARCH_ONLY
    evaluable: bool = True

    @property
    def failures(self) -> list[GateResult]:
        return [r for r in self.results if r.failed]

    @property
    def not_evaluable(self) -> list[GateResult]:
        return [r for r in self.results if r.outcome is GateOutcome.NOT_EVALUABLE]

    def summary(self) -> str:
        lines = [f"{'GATE':38s} {'OBSERVED':>12s} {'MIN':>8s} {'DESIRED':>8s}  RESULT"]
        lines.append("-" * 84)
        for r in self.results:
            observed = "n/a" if r.observed is None else f"{r.observed:.4f}"
            minimum = "-" if r.minimum is None else f"{r.minimum:g}"
            desired = "-" if r.desired is None else f"{r.desired:g}"
            lines.append(
                f"{r.name:38s} {observed:>12s} {minimum:>8s} {desired:>8s}  {r.outcome.value}"
            )
        if self.rejections:
            lines.append("")
            lines.append("AUTOMATIC REJECTION CONDITIONS TRIGGERED:")
            lines.extend(f"  - {reason}" for reason in self.rejections)
        lines.append("")
        lines.append(f"QUALIFICATION: {self.qualification.value}")
        return "\n".join(lines)


def _gate(
    name: str,
    observed: float | None,
    minimum: float | None,
    desired: float | None,
    *,
    higher_is_better: bool = True,
    note: str = "",
) -> GateResult:
    if observed is None:
        return GateResult(name, GateOutcome.NOT_EVALUABLE, None, minimum, desired, note)

    if minimum is not None:
        ok = observed >= minimum if higher_is_better else observed <= minimum
        if not ok:
            return GateResult(name, GateOutcome.FAIL, observed, minimum, desired, note)

    if desired is not None:
        met = observed >= desired if higher_is_better else observed <= desired
        if met:
            return GateResult(name, GateOutcome.DESIRED_MET, observed, minimum, desired, note)

    return GateResult(name, GateOutcome.PASS, observed, minimum, desired, note)


def evaluate_gates(
    oos: PerformanceMetrics,
    *,
    is_profit_factor: float | None = None,
    spread_stress_pf: float | None = None,
    monte_carlo_p95_dd: float | None = None,
    broker_profit_factors: dict[str, float] | None = None,
    max_year_contribution_pct: float | None = None,
    top5_profit_share: float | None = None,
) -> GateReport:
    """Apply the §43 acceptance gates and the §44 automatic rejection conditions.

    Missing inputs produce ``NOT_EVALUABLE`` gates — never a silent pass. A report
    containing any non-evaluable gate can not reach a candidate classification.
    """
    report = GateReport()
    r = report.results

    # ---- §43 provisional acceptance gates -----------------------------------
    r.append(_gate("OOS net profit factor", oos.profit_factor, 1.25, 1.35))
    r.append(_gate("OOS expectancy (R/trade)", oos.expectancy_r, 0.0, 0.10))
    r.append(
        _gate("OOS max drawdown %", oos.max_drawdown_pct, 15.0, 10.0,
              higher_is_better=False)
    )
    r.append(_gate("Recovery factor", oos.recovery_factor, 1.5, 2.0))
    r.append(_gate("Sharpe (annualized)", oos.sharpe, 0.5, 0.8))
    r.append(
        _gate("OOS trade count", float(oos.trades), 200.0, 300.0,
              note="a small sample cannot support a deployment decision")
    )

    degradation: float | None = None
    if is_profit_factor and oos.profit_factor is not None and is_profit_factor > 0:
        degradation = (is_profit_factor - oos.profit_factor) / is_profit_factor * 100.0
    r.append(
        _gate("PF degradation IS->OOS %", degradation, 30.0, 20.0, higher_is_better=False)
    )
    r.append(_gate("1.5x spread stress PF", spread_stress_pf, 1.0, 1.15))
    r.append(
        _gate("Monte Carlo P95 drawdown %", monte_carlo_p95_dd, 20.0, 15.0,
              higher_is_better=False)
    )

    # ---- §44 automatic rejection conditions ---------------------------------
    rejects = report.rejections
    if oos.profit_factor is not None and oos.profit_factor < 1.10:
        rejects.append(f"OOS profit factor {oos.profit_factor:.3f} < 1.10")
    if oos.trades > 0 and oos.expectancy_r <= 0:
        rejects.append(f"OOS expectancy {oos.expectancy_r:.4f} R <= 0")
    if oos.max_drawdown_pct > 20.0:
        rejects.append(f"OOS max drawdown {oos.max_drawdown_pct:.2f}% > 20%")
    if degradation is not None and degradation > 40.0:
        rejects.append(f"profit-factor collapse {degradation:.1f}% > 40% from IS to OOS")
    if spread_stress_pf is not None and spread_stress_pf < 1.0:
        rejects.append(f"1.5x spread stress profit factor {spread_stress_pf:.3f} < 1.0")
    if monte_carlo_p95_dd is not None and monte_carlo_p95_dd > 20.0:
        rejects.append(
            f"Monte Carlo P95 drawdown {monte_carlo_p95_dd:.2f}% exceeds the mandate"
        )
    if max_year_contribution_pct is not None and max_year_contribution_pct > 50.0:
        rejects.append(
            f"a single year contributes {max_year_contribution_pct:.1f}% of total profit"
        )
    share = top5_profit_share if top5_profit_share is not None else oos.top5_profit_share
    if share is not None and share > 0.80:
        rejects.append(f"the top 5 trades explain {share * 100:.1f}% of all profit")
    if broker_profit_factors:
        losing = {k: v for k, v in broker_profit_factors.items() if v < 1.0}
        if losing and len(losing) < len(broker_profit_factors):
            rejects.append(
                "profitable on some brokers but losing on "
                f"{sorted(losing)} — the edge is not portable"
            )

    # ---- classification ------------------------------------------------------
    report.evaluable = not report.not_evaluable
    if rejects:
        report.qualification = Qualification.REJECTED
    elif not report.evaluable or oos.trades == 0:
        # Cannot claim a candidate status on incomplete evidence.
        report.qualification = Qualification.RESEARCH_ONLY
    elif report.failures:
        report.qualification = Qualification.RESEARCH_ONLY
    else:
        strong = sum(1 for g in report.results if g.outcome is GateOutcome.DESIRED_MET)
        report.qualification = (
            Qualification.MICRO_LIVE_CANDIDATE
            if strong >= len(report.results) - 1
            else Qualification.FORWARD_TEST_CANDIDATE
        )
    return report
