"""Regime engine classification (spec §4).

The classification ORDER is normative, so these tests pin the precedence rules
(HIGH_VOLATILITY over trend; INVALID as the catch-all transition band) and not
merely the happy paths.
"""

from __future__ import annotations

import pytest
from research.strategies.xau_rpb import Regime, ResearchParams, classify

PARAMS = ResearchParams()


def _classify(**overrides: float) -> Regime:
    args: dict[str, float] = {
        "adx_value": 25.0,
        "normalized_spread": 0.5,
        "normalized_slope": 0.05,
        "er": 0.5,
        "atr_pct": 0.5,
    }
    args.update(overrides)
    return classify(params=PARAMS, **args)  # type: ignore[arg-type]


def test_aligned_bullish_inputs_give_trend_up() -> None:
    assert _classify() is Regime.TREND_UP


def test_aligned_bearish_inputs_give_trend_down() -> None:
    assert _classify(normalized_spread=-0.5, normalized_slope=-0.05) is Regime.TREND_DOWN


def test_high_volatility_dominates_an_otherwise_perfect_trend() -> None:
    # Every trend condition is satisfied, but volatility is at the extreme.
    assert _classify(atr_pct=0.96) is Regime.HIGH_VOLATILITY


def test_low_adx_gives_range() -> None:
    assert _classify(adx_value=10.0) is Regime.RANGE


def test_the_band_between_range_and_trend_is_invalid_not_tradeable() -> None:
    # adx 19 is >= adx_range_max (18) but < adx_trend_min (20): explicitly INVALID.
    assert _classify(adx_value=19.0) is Regime.INVALID


def test_strong_adx_without_ema_separation_is_invalid() -> None:
    assert _classify(normalized_spread=0.05) is Regime.INVALID


def test_strong_adx_without_slope_is_invalid() -> None:
    assert _classify(normalized_slope=0.001) is Regime.INVALID


def test_low_efficiency_ratio_blocks_a_trend_classification() -> None:
    # A choppy path to the same displacement is not a tradeable trend.
    assert _classify(er=0.1) is Regime.INVALID


def test_conflicting_spread_and_slope_never_produce_a_trend() -> None:
    assert _classify(normalized_spread=0.5, normalized_slope=-0.05) is Regime.INVALID
    assert _classify(normalized_spread=-0.5, normalized_slope=0.05) is Regime.INVALID


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_any_non_finite_input_fails_closed_to_invalid(bad: float) -> None:
    for field in ("adx_value", "normalized_spread", "normalized_slope", "er", "atr_pct"):
        assert _classify(**{field: bad}) is Regime.INVALID, f"{field} must fail closed"


def test_thresholds_are_inclusive_exactly_as_written() -> None:
    # adx >= adx_trend_min, spread >= spread_trend_min, slope >= slope_trend_min.
    assert _classify(adx_value=20.0, normalized_spread=0.25, normalized_slope=0.03) is (
        Regime.TREND_UP
    )
    # One tick below the spread threshold drops out of TREND_UP.
    assert _classify(normalized_spread=0.2499) is Regime.INVALID


def test_atr_pct_high_boundary_is_inclusive() -> None:
    assert _classify(atr_pct=0.95) is Regime.HIGH_VOLATILITY
    assert _classify(atr_pct=0.9499) is Regime.TREND_UP


def test_only_trend_states_are_tradeable() -> None:
    assert Regime.TREND_UP.is_tradeable and Regime.TREND_DOWN.is_tradeable
    assert not Regime.RANGE.is_tradeable
    assert not Regime.HIGH_VOLATILITY.is_tradeable
    assert not Regime.INVALID.is_tradeable
