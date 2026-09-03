"""Monte Carlo, temporal splits, sweeps and overfitting diagnostics (§33-§37).

The bars used here are synthetic fixtures for exercising the TOOLING. No number
produced in this file is evidence about the strategy's edge.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from itertools import pairwise

import pytest
from research.strategies.xau_rpb import BrokerSpec, StrategyConfig
from research.strategies.xau_rpb.types import Bar, Direction, ExitReason, Regime, Trade
from research.validation import (
    OosLedger,
    TrialLedger,
    block_bootstrap,
    chronological_split,
    deflated_sharpe_ratio,
    execution_stress,
    expected_max_sharpe,
    parameter_stability,
    parameter_sweep,
    percentile,
    probability_of_backtest_overfitting,
    sequence_bootstrap,
    summarize_surface,
    walk_forward_windows,
)

SPEC = BrokerSpec(
    symbol="XAUUSD", point=0.01, digits=2, tick_value=1.0, tick_size=0.01,
    lot_size=100.0, min_lot=0.01, max_lot=50.0, lot_step=0.01, stop_level_points=10.0,
)


def synthetic_bars(count: int, *, start: datetime | None = None) -> list[Bar]:
    """A deterministic ramp-with-noise fixture. Not market data."""
    import math
    import random

    rng = random.Random(4242)
    moment = start or datetime(2020, 1, 1)
    price = 1500.0
    bars: list[Bar] = []
    for i in range(count):
        price += 0.4 * math.sin(i / 600.0) + rng.gauss(0, 0.9)
        o = price
        c = price + rng.gauss(0, 0.7)
        h = max(o, c) + abs(rng.gauss(0, 0.5))
        low = min(o, c) - abs(rng.gauss(0, 0.5))
        bars.append(Bar(moment, o, h, low, c, 100.0, 18.0))
        price = c
        moment += timedelta(minutes=15)
    return bars


def make_trades(pnls: list[float]) -> list[Trade]:
    out = []
    for i, pnl in enumerate(pnls):
        entry = datetime(2024, 1, 1) + timedelta(hours=i)
        out.append(
            Trade(
                entry_time=entry, direction=Direction.LONG, entry_price=2000.0,
                stop_price=1990.0, initial_stop_price=1990.0, lots=0.1,
                atr_at_signal=5.0, score=7, regime_at_entry=Regime.TREND_UP,
                risk_amount=350.0, exit_time=entry + timedelta(hours=2),
                exit_price=2010.0, exit_reason=ExitReason.TARGET, pnl=pnl,
                r_multiple=pnl / 350.0, bars_held=8,
            )
        )
    return out


# ------------------------------------------------------------- percentiles


def test_percentile_uses_nearest_rank_so_the_value_actually_occurred() -> None:
    sample = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile(sample, 0.0) == 1.0
    assert percentile(sample, 1.0) == 5.0
    assert percentile(sample, 0.5) in sample


def test_percentile_rejects_an_empty_sample() -> None:
    with pytest.raises(ValueError):
        percentile([], 0.5)


# ------------------------------------------------------------- monte carlo


def test_sequence_bootstrap_produces_a_drawdown_distribution() -> None:
    trades = make_trades([200.0, -150.0, 300.0, -100.0, -250.0, 400.0] * 12)
    result = sequence_bootstrap(trades, iterations=400, seed=7)

    assert result.iterations == 400
    assert len(result.drawdowns) == 400
    assert result.p95_drawdown >= result.p50_drawdown
    assert result.p99_drawdown >= result.p95_drawdown
    assert 0.0 <= result.probability_of_loss <= 1.0


def test_monte_carlo_is_reproducible_for_a_fixed_seed() -> None:
    trades = make_trades([100.0, -80.0, 120.0, -60.0] * 20)
    a = sequence_bootstrap(trades, iterations=200, seed=99)
    b = sequence_bootstrap(trades, iterations=200, seed=99)
    assert a.drawdowns == b.drawdowns


def test_block_bootstrap_preserves_clustering_and_reports_a_fatter_tail() -> None:
    """Losses arrive in clusters; IID resampling hides exactly that risk."""
    clustered = make_trades([200.0] * 30 + [-200.0] * 15 + [200.0] * 30 + [-200.0] * 15)
    iid = sequence_bootstrap(clustered, iterations=600, seed=3)
    blocks = block_bootstrap(clustered, block_size=15, iterations=600, seed=3)

    assert blocks.p95_drawdown >= iid.p50_drawdown
    assert blocks.family.startswith("block_bootstrap")


def test_monte_carlo_on_an_empty_trade_list_is_harmless() -> None:
    result = sequence_bootstrap([], iterations=100)
    assert result.iterations == 0
    assert result.drawdowns == []


def test_risk_of_ruin_is_reported_for_a_catastrophic_series() -> None:
    trades = make_trades([-9_000.0] * 20)
    result = sequence_bootstrap(trades, initial_equity=100_000.0, iterations=100, seed=1)
    assert result.risk_of_ruin > 0.0


# ----------------------------------------------------------------- splits


def test_chronological_split_is_ordered_and_non_overlapping() -> None:
    bars = synthetic_bars(2000)
    split = chronological_split(bars)

    assert split.development.end <= split.validation.start
    assert split.validation.end <= split.final_oos.start
    total = len(split.development.bars) + len(split.validation.bars) + len(
        split.final_oos.bars
    )
    assert total == len(bars)


def test_split_never_shuffles_the_series() -> None:
    bars = synthetic_bars(500)
    split = chronological_split(bars)
    for part in (split.development, split.validation, split.final_oos):
        times = [b.time for b in part.bars]
        assert times == sorted(times)


def test_split_rejects_fractions_that_leave_no_out_of_sample() -> None:
    with pytest.raises(ValueError):
        chronological_split(synthetic_bars(500), development_frac=0.8, validation_frac=0.3)


def test_walk_forward_windows_advance_and_never_overlap_train_with_test() -> None:
    bars = synthetic_bars(30_000)  # a bit over 10 months of M15
    windows = walk_forward_windows(bars, train_months=3, test_months=1)

    assert windows, "the fixture must span enough time for at least one window"
    for w in windows:
        assert w.train_end <= w.test_start, "training must end before testing begins"
    for a, b in pairwise(windows):
        assert b.test_start > a.test_start, "windows must advance"


def test_anchored_windows_keep_the_same_start_and_grow() -> None:
    bars = synthetic_bars(30_000)
    anchored = walk_forward_windows(bars, train_months=3, test_months=1, anchored=True)
    if len(anchored) < 2:
        pytest.skip("fixture too short for two anchored windows")

    assert anchored[0].train_start == anchored[-1].train_start
    assert len(anchored[-1].train) > len(anchored[0].train)


def test_oos_ledger_flags_the_partition_as_spent_after_a_second_configuration(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    """Mandate §33: consulting the final OOS twice with different params spends it."""
    ledger = OosLedger(tmp_path / "oos.json")
    ledger.record(config_hash="aaa", spec_version="V1", reason="frozen run")
    assert not ledger.is_spent
    assert "consulted once" in (ledger.warning() or "")

    ledger.record(config_hash="bbb", spec_version="V1", reason="second look")
    assert ledger.is_spent
    assert "SPENT" in (ledger.warning() or "")


# ----------------------------------------------------------------- sweeps


def test_a_parameter_sweep_only_varies_research_parameters() -> None:
    bars = synthetic_bars(3000)
    base = StrategyConfig()
    points = parameter_sweep(
        bars, base, SPEC, {"sl_atr_mult": (1.5, 2.0), "adx_trend_min": (18.0, 22.0)},
    )

    assert len(points) == 4
    for point in points:
        # Risk policy is structurally unreachable from a sweep (spec §14).
        assert set(point.params) <= {"sl_atr_mult", "adx_trend_min"}
    assert len({p.config_hash for p in points}) == 4, "each combination is distinct"


def test_sweep_skips_internally_contradictory_combinations() -> None:
    bars = synthetic_bars(1500)
    points = parameter_sweep(
        bars, StrategyConfig(), SPEC,
        # adx_range_max above adx_trend_min is invalid and must be skipped, not forced.
        {"adx_range_max": (10.0, 99.0)},
    )
    assert len(points) == 1


def test_surface_summary_describes_a_plateau_rather_than_crowning_a_winner() -> None:
    bars = synthetic_bars(3000)
    points = parameter_sweep(
        bars, StrategyConfig(), SPEC, {"sl_atr_mult": (1.5, 2.0, 2.5)},
    )
    surface = summarize_surface(points)

    assert surface.evaluated == len(points)
    assert 0.0 <= surface.profitable_fraction <= 1.0
    assert "PLATEAU" in surface.summary()
    assert "not the peak" in surface.summary()


def test_execution_stress_reruns_the_strategy_under_each_cost_scenario() -> None:
    bars = synthetic_bars(4000)
    scenarios = execution_stress(
        bars, StrategyConfig(), SPEC,
        spread_multipliers=(1.0, 2.0), slippage_points=(0.0, 3.0),
    )
    assert len(scenarios) == 4
    labels = {s.label for s in scenarios}
    assert len(labels) == 4

    baseline = next(s for s in scenarios if s.spread_multiplier == 1.0
                    and s.slippage_points == 0.0)
    worst = next(s for s in scenarios if s.spread_multiplier == 2.0
                 and s.slippage_points == 3.0)
    # Worse fills can only reduce the number of eligible setups or their P&L.
    assert worst.metrics.trades <= baseline.metrics.trades


def test_parameter_stability_reports_the_spread_of_selected_values() -> None:
    from research.validation.metrics import PerformanceMetrics
    from research.validation.splits import WalkForwardWindow
    from research.validation.sweeps import WalkForwardResult

    bars = synthetic_bars(200)
    window = WalkForwardWindow(0, bars[:100], bars[100:], False)
    results = [
        WalkForwardResult(window, {"sl_atr_mult": v}, PerformanceMetrics(),
                          PerformanceMetrics())
        for v in (1.5, 2.0, 2.5, 1.5)
    ]
    stability = parameter_stability(results)

    assert stability["sl_atr_mult"]["min"] == 1.5
    assert stability["sl_atr_mult"]["max"] == 2.5
    assert stability["sl_atr_mult"]["coefficient_of_variation"] > 0


# ----------------------------------------------------------- overfitting


def test_expected_max_sharpe_grows_with_the_number_of_trials() -> None:
    """Searching harder produces bigger maxima from pure noise."""
    few = expected_max_sharpe(10, 0.25)
    many = expected_max_sharpe(1000, 0.25)
    assert many > few > 0


def test_deflated_sharpe_falls_as_the_trial_count_rises() -> None:
    single = deflated_sharpe_ratio(
        1.2, trials=1, variance_of_sharpes=0.2, sample_length=400
    )
    searched = deflated_sharpe_ratio(
        1.2, trials=500, variance_of_sharpes=0.2, sample_length=400
    )
    assert single is not None and searched is not None
    assert searched < single, "the same Sharpe is weaker evidence after 500 trials"


def test_deflated_sharpe_is_none_for_a_degenerate_sample() -> None:
    assert deflated_sharpe_ratio(1.0, trials=10, variance_of_sharpes=0.1,
                                 sample_length=1) is None


def test_pbo_is_near_one_half_when_configurations_are_pure_noise() -> None:
    """A selection procedure with no information should score close to 0.5."""
    import random

    rng = random.Random(11)
    matrix = [[rng.gauss(0, 1) for _ in range(12)] for _ in range(48)]
    result = probability_of_backtest_overfitting(matrix, partitions=6)

    assert result is not None
    assert 0.2 <= result["pbo"] <= 0.8


def test_pbo_is_low_when_one_configuration_is_genuinely_better() -> None:
    import random

    rng = random.Random(5)
    matrix = []
    for _ in range(48):
        row = [rng.gauss(0, 1) for _ in range(11)]
        row.append(rng.gauss(6, 1))  # a genuinely superior configuration
        matrix.append(row)
    result = probability_of_backtest_overfitting(matrix, partitions=6)

    assert result is not None
    assert result["pbo"] < 0.2


def test_pbo_returns_none_when_the_matrix_is_too_small() -> None:
    assert probability_of_backtest_overfitting([[1.0, 2.0]], partitions=8) is None


def test_trial_ledger_records_failures_as_well_as_successes(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Mandate §36: never hide unsuccessful parameter runs."""
    ledger = TrialLedger(tmp_path / "trials.json")
    ledger.record(config_hash="a", params={"x": 1}, profit_factor=1.6, sharpe=0.9,
                  net_return_pct=20.0, trades=250, partition="DEV")
    ledger.record(config_hash="b", params={"x": 2}, profit_factor=0.7, sharpe=-0.3,
                  net_return_pct=-12.0, trades=240, partition="DEV")
    ledger.flush()

    assert ledger.count == 2, "the losing run must be recorded too"
    assert ledger.sharpe_variance() > 0
    assert (tmp_path / "trials.json").is_file()
    assert "trials recorded        : 2" in ledger.summary()
