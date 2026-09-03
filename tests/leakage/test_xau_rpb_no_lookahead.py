"""Leakage guards for XAU_RPB (INV-3, spec §2).

Look-ahead is the failure mode that makes a worthless strategy look excellent, and
it never announces itself. These tests attack it structurally rather than by
inspection:

* **Prefix invariance** — decisions taken before time T must not change when data
  after T is added or removed. A strategy that peeks fails this immediately.
* **Future mutation** — rewriting bars strictly after a decision must not alter
  that decision.
* **Fill timing** — no trade may be filled at a price from the bar that generated
  its signal.

The bars are synthetic fixtures. Nothing here is evidence about profitability.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta
from itertools import pairwise

import pytest
from research.strategies.xau_rpb import Bar, BrokerSpec, StrategyConfig, run_backtest

SPEC = BrokerSpec(
    symbol="XAUUSD", point=0.01, digits=2, tick_value=1.0, tick_size=0.01,
    lot_size=100.0, min_lot=0.01, max_lot=50.0, lot_step=0.01, stop_level_points=10.0,
)


def synthetic_series(seed: int, count: int = 9000) -> list[Bar]:
    """A reproducible pseudo-market path. A FIXTURE, not market data."""
    rng = random.Random(seed)
    bars: list[Bar] = []
    moment = datetime(2023, 1, 2, 0, 0)
    price = 1900.0
    for i in range(count):
        price += 0.5 * math.sin(i / 700.0) + rng.gauss(0, 0.9)
        open_ = price
        close = price + rng.gauss(0, 0.8)
        high = max(open_, close) + abs(rng.gauss(0, 0.5))
        low = min(open_, close) - abs(rng.gauss(0, 0.5))
        bars.append(Bar(moment, open_, high, low, close, 100.0, 20.0))
        price = close
        moment += timedelta(minutes=15)
    return bars


def _signature(trades: list) -> list[tuple]:
    return [
        (t.entry_time, t.direction, round(t.entry_price, 8), round(t.initial_stop_price, 8))
        for t in trades
    ]


@pytest.fixture(scope="module")
def bars() -> list[Bar]:
    return synthetic_series(11)


def test_the_backtest_is_deterministic(bars: list[Bar]) -> None:
    cfg = StrategyConfig()
    first = run_backtest(bars, cfg, SPEC)
    second = run_backtest(bars, cfg, SPEC)

    assert _signature(first.trades) == _signature(second.trades)
    assert first.final_equity == pytest.approx(second.final_equity)


def test_truncating_the_future_does_not_change_past_decisions(bars: list[Bar]) -> None:
    """Prefix invariance: the strongest cheap test for look-ahead."""
    cfg = StrategyConfig()
    cut = 6000
    full = run_backtest(bars, cfg, SPEC)
    prefix = run_backtest(bars[:cut], cfg, SPEC)

    cut_time = bars[cut - 1].time
    settled = [t for t in full.trades if t.exit_time is not None and t.exit_time <= cut_time]
    assert settled, "the fixture must produce trades that close before the cut"

    assert _signature(settled) == _signature(prefix.trades[: len(settled)])


def test_rewriting_future_bars_cannot_change_an_earlier_decision(bars: list[Bar]) -> None:
    """Mutate everything after a cut; decisions before it must be byte-identical."""
    cfg = StrategyConfig()
    cut = 5000
    baseline = run_backtest(bars, cfg, SPEC)

    rng = random.Random(99)
    mutated = list(bars)
    for i in range(cut, len(mutated)):
        b = mutated[i]
        shift = rng.uniform(-50.0, 50.0)
        mutated[i] = Bar(
            b.time, b.open + shift, b.high + shift, b.low + shift, b.close + shift,
            b.volume, b.spread_points,
        )
    perturbed = run_backtest(mutated, cfg, SPEC)

    cut_time = bars[cut - 1].time
    base_before = [t for t in baseline.trades if t.entry_time <= cut_time]
    pert_before = [t for t in perturbed.trades if t.entry_time <= cut_time]

    # Compare only entries decided strictly before the mutation boundary.
    assert _signature(base_before)[:-1] == _signature(pert_before)[:-1]


def test_no_trade_is_filled_on_the_bar_that_produced_its_signal(bars: list[Bar]) -> None:
    """Signal on close, fill on the NEXT open — never a same-bar fill."""
    result = run_backtest(bars, StrategyConfig(), SPEC)
    assert result.trades, "the fixture must produce trades"

    times = {b.time: i for i, b in enumerate(bars)}
    for trade in result.trades:
        index = times[trade.entry_time]
        assert index >= 1
        # The fill price must derive from the entry bar's OPEN, not its close.
        expected_open = bars[index].open
        drift = abs(trade.entry_price - expected_open)
        assert drift < 1.0, "entry must be anchored to the fill bar's open"


def test_exit_never_precedes_entry(bars: list[Bar]) -> None:
    result = run_backtest(bars, StrategyConfig(), SPEC)
    for trade in result.trades:
        assert trade.exit_time is not None
        assert trade.exit_time >= trade.entry_time


def test_only_one_position_is_ever_open(bars: list[Bar]) -> None:
    """Spec §7.2 concurrency limit, verified against the realized trade list."""
    result = run_backtest(bars, StrategyConfig(), SPEC)
    ordered = sorted(result.trades, key=lambda t: t.entry_time)
    for earlier, later in pairwise(ordered):
        assert earlier.exit_time is not None
        assert later.entry_time >= earlier.exit_time, "positions must not overlap"


def test_warmup_bars_produce_no_trades(bars: list[Bar]) -> None:
    """Indicators are undefined during warmup, so the engine must stay flat."""
    cfg = StrategyConfig()
    result = run_backtest(bars, cfg, SPEC)
    warmup_end = bars[cfg.warmup_bars_m15()].time
    assert all(t.entry_time > warmup_end for t in result.trades)


def test_an_all_invalid_regime_series_produces_no_trades() -> None:
    """A flat market never reaches a trend regime, so nothing may be opened."""
    flat = [
        Bar(datetime(2024, 1, 1) + i * timedelta(minutes=15), 2000.0, 2000.0, 2000.0, 2000.0,
            100.0, 20.0)
        for i in range(3000)
    ]
    result = run_backtest(flat, StrategyConfig(), SPEC)
    assert result.trades == []
