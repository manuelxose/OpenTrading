"""Metrics (mandate §42) and the frozen acceptance gates (§43, §44).

The gate tests matter more than they look: they pin the thresholds so that
relaxing one becomes a visible, reviewable diff rather than a quiet edit after a
disappointing run.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from research.strategies.xau_rpb.types import Direction, ExitReason, Regime, Trade
from research.validation import (
    GateOutcome,
    PerformanceMetrics,
    Qualification,
    compute_metrics,
    evaluate_gates,
    max_drawdown,
    side_breakdown,
    yearly_breakdown,
)

START = datetime(2024, 1, 2, 9, 0)


def trade(
    pnl: float,
    *,
    day: int = 1,
    direction: Direction = Direction.LONG,
    r_multiple: float | None = None,
    year: int = 2024,
) -> Trade:
    entry = datetime(year, 1, 1) + timedelta(days=day)
    return Trade(
        entry_time=entry,
        direction=direction,
        entry_price=2000.0,
        stop_price=1990.0,
        initial_stop_price=1990.0,
        lots=0.1,
        atr_at_signal=5.0,
        score=7,
        regime_at_entry=Regime.TREND_UP,
        risk_amount=350.0,
        exit_time=entry + timedelta(hours=6),
        exit_price=2010.0 if pnl > 0 else 1990.0,
        exit_reason=ExitReason.TARGET if pnl > 0 else ExitReason.STOP_LOSS,
        pnl=pnl,
        r_multiple=r_multiple if r_multiple is not None else (pnl / 350.0),
        bars_held=24,
    )


def equity_from(trades: list[Trade], initial: float = 100_000.0) -> list:
    curve = [(START, initial)]
    running = initial
    for i, t in enumerate(trades, start=1):
        running += t.pnl
        curve.append((START + timedelta(hours=i), running))
    return curve


# ------------------------------------------------------------------ metrics


def test_profit_factor_and_expectancy_are_computed_from_realized_trades() -> None:
    trades = [trade(300.0), trade(300.0), trade(-200.0)]
    m = compute_metrics(trades, equity_from(trades), 100_000.0)

    assert m.trades == 3
    assert m.wins == 2 and m.losses == 1
    assert m.profit_factor == pytest.approx(600.0 / 200.0)
    assert m.expectancy == pytest.approx(400.0 / 3.0)
    assert m.win_rate == pytest.approx(2 / 3)


def test_profit_factor_is_none_rather_than_infinite_when_there_are_no_losses() -> None:
    """An undefined metric must never be reported as a flattering number."""
    trades = [trade(100.0), trade(50.0)]
    m = compute_metrics(trades, equity_from(trades), 100_000.0)
    assert m.profit_factor is None


def test_empty_trade_list_yields_a_zeroed_but_valid_metric_set() -> None:
    m = compute_metrics([], [(START, 100_000.0)], 100_000.0)
    assert m.trades == 0
    assert m.profit_factor is None
    assert m.max_drawdown_pct == 0.0


def test_max_drawdown_is_measured_from_the_running_peak() -> None:
    pct, absolute = max_drawdown([100.0, 120.0, 90.0, 130.0])
    assert pct == pytest.approx(25.0)
    assert absolute == pytest.approx(30.0)


def test_losing_and_winning_streaks_are_tracked() -> None:
    trades = [trade(-10.0), trade(-10.0), trade(-10.0), trade(50.0), trade(50.0)]
    m = compute_metrics(trades, equity_from(trades), 100_000.0)
    assert m.max_losing_streak == 3
    assert m.max_winning_streak == 2


def test_top5_profit_share_exposes_concentration() -> None:
    """Mandate §44: a result explained by a handful of trades is a rejection signal."""
    trades = [trade(10_000.0)] + [trade(10.0) for _ in range(50)]
    m = compute_metrics(trades, equity_from(trades), 100_000.0)
    assert m.top5_profit_share is not None
    assert m.top5_profit_share > 0.90


def test_side_breakdown_reports_each_direction_separately() -> None:
    """A combined curve must not hide a structurally broken side (mandate §39)."""
    trades = [
        trade(500.0, direction=Direction.LONG),
        trade(500.0, direction=Direction.LONG),
        trade(-400.0, direction=Direction.SHORT),
        trade(-400.0, direction=Direction.SHORT),
    ]
    sides = side_breakdown(trades, equity_from(trades), 100_000.0)

    assert sides.long.net_profit == pytest.approx(1000.0)
    assert sides.short.net_profit == pytest.approx(-800.0)
    assert sides.combined.net_profit == pytest.approx(200.0)
    assert sides.short.profit_factor is None or sides.short.profit_factor < 1.0


def test_yearly_breakdown_exposes_a_dominant_year() -> None:
    trades = [trade(9_000.0, year=2022)] + [trade(100.0, year=2023) for _ in range(10)]
    years = yearly_breakdown(trades)
    dominant = max(years, key=lambda y: y.contribution_pct)
    assert dominant.year == 2022
    assert dominant.contribution_pct > 50.0


# -------------------------------------------------------------------- gates


def passing_metrics() -> PerformanceMetrics:
    m = PerformanceMetrics()
    m.trades = 400
    m.profit_factor = 1.45
    m.expectancy_r = 0.15
    m.max_drawdown_pct = 8.0
    m.recovery_factor = 2.4
    m.sharpe = 0.95
    return m


def test_a_strong_result_reaches_a_candidate_classification() -> None:
    report = evaluate_gates(
        passing_metrics(), is_profit_factor=1.55, spread_stress_pf=1.3,
        monte_carlo_p95_dd=11.0, max_year_contribution_pct=30.0,
    )
    assert not report.failures
    assert not report.rejections
    assert report.qualification in (
        Qualification.FORWARD_TEST_CANDIDATE, Qualification.MICRO_LIVE_CANDIDATE
    )


def test_missing_evidence_never_silently_passes_a_gate() -> None:
    """An un-evaluated gate is NOT_EVALUABLE, and blocks a candidate status."""
    report = evaluate_gates(passing_metrics())

    assert report.not_evaluable, "absent inputs must surface as non-evaluable gates"
    assert report.qualification is Qualification.RESEARCH_ONLY


def test_a_weak_profit_factor_triggers_automatic_rejection() -> None:
    m = passing_metrics()
    m.profit_factor = 1.05
    report = evaluate_gates(m, is_profit_factor=1.1, spread_stress_pf=1.2,
                            monte_carlo_p95_dd=10.0, max_year_contribution_pct=20.0)
    assert report.qualification is Qualification.REJECTED
    assert any("profit factor" in r for r in report.rejections)


def test_non_positive_expectancy_triggers_rejection() -> None:
    m = passing_metrics()
    m.expectancy_r = -0.02
    report = evaluate_gates(m, is_profit_factor=1.5, spread_stress_pf=1.2,
                            monte_carlo_p95_dd=10.0, max_year_contribution_pct=20.0)
    assert report.qualification is Qualification.REJECTED


def test_excessive_drawdown_triggers_rejection() -> None:
    m = passing_metrics()
    m.max_drawdown_pct = 24.0
    report = evaluate_gates(m, is_profit_factor=1.5, spread_stress_pf=1.2,
                            monte_carlo_p95_dd=10.0, max_year_contribution_pct=20.0)
    assert report.qualification is Qualification.REJECTED


def test_profit_factor_collapse_from_is_to_oos_triggers_rejection() -> None:
    m = passing_metrics()
    m.profit_factor = 1.30
    report = evaluate_gates(m, is_profit_factor=2.6, spread_stress_pf=1.2,
                            monte_carlo_p95_dd=10.0, max_year_contribution_pct=20.0)
    assert report.qualification is Qualification.REJECTED
    assert any("collapse" in r for r in report.rejections)


def test_failing_the_spread_stress_triggers_rejection() -> None:
    report = evaluate_gates(passing_metrics(), is_profit_factor=1.5,
                            spread_stress_pf=0.92, monte_carlo_p95_dd=10.0,
                            max_year_contribution_pct=20.0)
    assert report.qualification is Qualification.REJECTED


def test_a_single_dominant_year_triggers_rejection() -> None:
    report = evaluate_gates(passing_metrics(), is_profit_factor=1.5,
                            spread_stress_pf=1.2, monte_carlo_p95_dd=10.0,
                            max_year_contribution_pct=64.0)
    assert report.qualification is Qualification.REJECTED
    assert any("single year" in r for r in report.rejections)


def test_an_edge_that_works_on_only_some_brokers_is_rejected() -> None:
    report = evaluate_gates(
        passing_metrics(), is_profit_factor=1.5, spread_stress_pf=1.2,
        monte_carlo_p95_dd=10.0, max_year_contribution_pct=20.0,
        broker_profit_factors={"A": 1.6, "B": 0.85, "C": 0.79},
    )
    assert report.qualification is Qualification.REJECTED
    assert any("not portable" in r for r in report.rejections)


def test_profit_concentrated_in_five_trades_is_rejected() -> None:
    report = evaluate_gates(
        passing_metrics(), is_profit_factor=1.5, spread_stress_pf=1.2,
        monte_carlo_p95_dd=10.0, max_year_contribution_pct=20.0,
        top5_profit_share=0.93,
    )
    assert report.qualification is Qualification.REJECTED


def test_a_thin_sample_fails_the_trade_count_gate() -> None:
    m = passing_metrics()
    m.trades = 40
    report = evaluate_gates(m, is_profit_factor=1.5, spread_stress_pf=1.2,
                            monte_carlo_p95_dd=10.0, max_year_contribution_pct=20.0)
    failed = {g.name for g in report.failures}
    assert "OOS trade count" in failed
    assert report.qualification is Qualification.RESEARCH_ONLY


@pytest.mark.parametrize(
    "name,minimum",
    [
        ("OOS net profit factor", 1.25),
        ("OOS max drawdown %", 15.0),
        ("Recovery factor", 1.5),
        ("Sharpe (annualized)", 0.5),
        ("OOS trade count", 200.0),
        ("1.5x spread stress PF", 1.0),
        ("Monte Carlo P95 drawdown %", 20.0),
    ],
)
def test_gate_thresholds_are_frozen_at_the_mandated_values(name: str, minimum: float) -> None:
    """Pinning the thresholds makes any future relaxation a visible diff."""
    report = evaluate_gates(passing_metrics(), is_profit_factor=1.5,
                            spread_stress_pf=1.2, monte_carlo_p95_dd=10.0)
    gate = next(g for g in report.results if g.name == name)
    assert gate.minimum == pytest.approx(minimum)


def test_the_report_renders_a_readable_summary() -> None:
    report = evaluate_gates(passing_metrics(), is_profit_factor=1.5,
                            spread_stress_pf=1.2, monte_carlo_p95_dd=10.0,
                            max_year_contribution_pct=20.0)
    text = report.summary()
    assert "QUALIFICATION:" in text
    assert GateOutcome.PASS.value in text or GateOutcome.DESIRED_MET.value in text
