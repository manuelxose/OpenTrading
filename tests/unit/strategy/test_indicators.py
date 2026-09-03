"""Indicator correctness against the normative definitions of spec §3.1.

These are pinned by hand-computable cases rather than by comparison with a
library, because the spec — not a library's defaults — is the contract the MQL4
mirror must also satisfy.
"""

from __future__ import annotations

import math

import pytest
from research.strategies.xau_rpb.indicators import (
    adx,
    atr,
    atr_percentile,
    efficiency_ratio,
    ema,
    true_range,
    wilder_rma,
)

from xau_rpb_builders import bar


def test_ema_is_undefined_before_the_seed_and_seeds_with_the_sma() -> None:
    values = [10.0, 11.0, 12.0, 13.0, 14.0]
    out = ema(values, 3)

    assert all(math.isnan(v) for v in out[:2]), "EMA must be undefined before the seed"
    assert out[2] == pytest.approx(11.0), "seed is the SMA of the first 3 values"
    alpha = 2.0 / 4.0
    assert out[3] == pytest.approx(13.0 * alpha + 11.0 * (1 - alpha))
    assert out[4] == pytest.approx(14.0 * alpha + out[3] * (1 - alpha))


def test_ema_returns_all_nan_when_history_is_shorter_than_the_period() -> None:
    assert all(math.isnan(v) for v in ema([1.0, 2.0], 5))


def test_true_range_uses_the_previous_close() -> None:
    bars = [bar(0, 100, 105, 95, 102), bar(1, 102, 110, 101, 108)]
    tr = true_range(bars)

    assert math.isnan(tr[0]), "TR needs a previous close, so index 0 is undefined"
    # max(high-low=9, |high-prev_close|=8, |low-prev_close|=1)
    assert tr[1] == pytest.approx(9.0)


def test_true_range_picks_the_gap_branch_when_price_gaps_up() -> None:
    bars = [bar(0, 100, 101, 99, 100), bar(1, 120, 122, 119, 121)]
    tr = true_range(bars)
    # high-low = 3, but |high - prev_close| = 22 dominates.
    assert tr[1] == pytest.approx(22.0)


def test_atr_seeds_with_the_mean_of_the_first_n_true_ranges() -> None:
    bars = [bar(i, 100 + i, 101 + i, 99 + i, 100 + i) for i in range(6)]
    out = atr(bars, 3)

    assert all(math.isnan(v) for v in out[:3])
    tr = true_range(bars)
    assert out[3] == pytest.approx((tr[1] + tr[2] + tr[3]) / 3.0)
    assert out[4] == pytest.approx((out[3] * 2 + tr[4]) / 3.0), "Wilder smoothing thereafter"


def test_wilder_rma_never_consumes_a_nan_from_before_start() -> None:
    values = [float("nan"), 2.0, 4.0, 6.0, 8.0]
    out = wilder_rma(values, 2, start=1)

    assert math.isnan(out[0]) and math.isnan(out[1])
    assert out[2] == pytest.approx(3.0)
    assert not any(math.isnan(v) for v in out[2:])


def test_efficiency_ratio_is_one_for_a_perfectly_straight_move() -> None:
    closes = [float(i) for i in range(11)]
    out = efficiency_ratio(closes, 5)
    assert out[10] == pytest.approx(1.0), "monotone path: displacement == path length"


def test_efficiency_ratio_is_zero_when_price_returns_to_its_origin() -> None:
    closes = [10.0, 11.0, 10.0, 11.0, 10.0, 11.0, 10.0]
    out = efficiency_ratio(closes, 6)
    assert out[6] == pytest.approx(0.0)


def test_efficiency_ratio_is_zero_when_the_path_length_is_zero() -> None:
    out = efficiency_ratio([5.0] * 6, 5)
    assert out[5] == pytest.approx(0.0), "flat series must not divide by zero"


def test_adx_is_undefined_until_twice_the_period() -> None:
    bars = [bar(i, 100 + i, 101 + i, 99 + i, 100.5 + i) for i in range(40)]
    out = adx(bars, 14)

    assert math.isnan(out[26]), "ADX needs 2n-1 bars before it is defined"
    assert not math.isnan(out[27])
    assert 0.0 <= out[30] <= 100.0


def test_adx_is_high_for_a_clean_one_way_trend() -> None:
    bars = [bar(i, 100 + 2 * i, 101 + 2 * i, 99.5 + 2 * i, 100.8 + 2 * i) for i in range(60)]
    out = adx(bars, 14)
    assert out[-1] > 40.0, "a monotone ramp must register as strongly directional"


def test_adx_stays_low_in_a_tight_oscillation() -> None:
    bars = []
    for i in range(80):
        base = 100 + (1.0 if i % 2 else 0.0)
        bars.append(bar(i, base, base + 0.3, base - 0.3, base))
    out = adx(bars, 14)
    assert out[-1] < 30.0, "an alternating chop must not register as a trend"


def test_atr_percentile_counts_strictly_smaller_values() -> None:
    series = [1.0, 2.0, 3.0, 4.0, 5.0]
    out = atr_percentile(series, 5)

    assert math.isnan(out[3]), "undefined until a full window exists"
    assert out[4] == pytest.approx(0.8), "4 of 5 values are strictly below the last"


def test_atr_percentile_treats_ties_as_not_below() -> None:
    out = atr_percentile([2.0, 2.0, 2.0, 2.0], 4)
    assert out[3] == pytest.approx(0.0), "ties must not count, keeping the statistic monotone"


def test_atr_percentile_skips_windows_containing_undefined_values() -> None:
    out = atr_percentile([float("nan"), 1.0, 2.0], 3)
    assert math.isnan(out[2])


@pytest.mark.parametrize("period", [0, -1])
def test_indicators_reject_a_non_positive_period(period: int) -> None:
    with pytest.raises(ValueError):
        ema([1.0, 2.0, 3.0], period)
    with pytest.raises(ValueError):
        efficiency_ratio([1.0, 2.0, 3.0], period)
