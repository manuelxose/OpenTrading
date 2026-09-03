"""H1 market regime engine (spec §4).

Deterministic and interpretable by construction: no machine learning, no fitted
classifier, no probability. The classification order in :func:`classify` is
normative — HIGH_VOLATILITY dominates trend, and INVALID is the catch-all for the
transition band between ``adx_range_max`` and ``adx_trend_min``.

Every input is read from a CLOSED bar (spec §2). The caller passes the index of
the last closed H1 bar; nothing at a later index is reachable from here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .config import ResearchParams
from .indicators import adx, atr, atr_percentile, efficiency_ratio, ema, is_finite
from .types import Bar, Regime

__all__ = ["RegimeFeatures", "RegimeSeries", "classify", "compute_regime_series"]


@dataclass(frozen=True, slots=True)
class RegimeFeatures:
    """The H1 feature vector behind one regime decision (logged verbatim, spec §28)."""

    regime: Regime
    ema_fast: float
    ema_slow: float
    atr_h1: float
    adx: float
    er: float
    atr_pct: float
    normalized_spread: float
    normalized_slope: float

    @classmethod
    def invalid(cls) -> RegimeFeatures:
        nan = float("nan")
        return cls(Regime.INVALID, nan, nan, nan, nan, nan, nan, nan, nan)


def classify(
    *,
    adx_value: float,
    normalized_spread: float,
    normalized_slope: float,
    er: float,
    atr_pct: float,
    params: ResearchParams,
) -> Regime:
    """Pure classification function (spec §4.1). First match wins, order is normative."""
    inputs = (adx_value, normalized_spread, normalized_slope, er, atr_pct)
    if not all(is_finite(v) for v in inputs):
        return Regime.INVALID

    # 2. Risk-off dominates: a violent trend is still a regime we do not trade.
    if atr_pct >= params.atr_pct_high:
        return Regime.HIGH_VOLATILITY

    trending = adx_value >= params.adx_trend_min and er >= params.er_trend_min
    if trending:
        if (
            normalized_spread >= params.spread_trend_min
            and normalized_slope >= params.slope_trend_min
        ):
            return Regime.TREND_UP
        if (
            normalized_spread <= -params.spread_trend_min
            and normalized_slope <= -params.slope_trend_min
        ):
            return Regime.TREND_DOWN

    # 5. Quiet, directionless market.
    if adx_value < params.adx_range_max:
        return Regime.RANGE

    # 6. The transition band, and trending-but-not-aligned: explicitly not tradeable.
    return Regime.INVALID


class RegimeSeries:
    """Pre-computes the H1 feature series once, then answers per-closed-bar queries.

    Computing the whole series up front is safe with respect to INV-3 because each
    indicator at index ``i`` depends only on bars ``<= i``; :meth:`at` never exposes
    an index the caller has not already reached.
    """

    def __init__(self, bars: Sequence[Bar], params: ResearchParams) -> None:
        self._bars = bars
        self._params = params
        closes = [b.close for b in bars]
        self._ema_fast = ema(closes, params.ema_fast_period)
        self._ema_slow = ema(closes, params.ema_slow_period)
        self._atr = atr(bars, params.atr_period_h1)
        self._adx = adx(bars, params.adx_period)
        self._er = efficiency_ratio(closes, params.er_window)
        self._atr_pct = atr_percentile(self._atr, params.atr_pct_window)

    def __len__(self) -> int:
        return len(self._bars)

    def at(self, index: int) -> RegimeFeatures:
        """Regime as of the CLOSED H1 bar at ``index`` (the spec's ``shift = 1``)."""
        p = self._params
        if index < 0 or index >= len(self._bars):
            return RegimeFeatures.invalid()

        slope_index = index - p.slope_lookback
        if slope_index < 0:
            return RegimeFeatures.invalid()

        ema_fast = self._ema_fast[index]
        ema_slow = self._ema_slow[index]
        ema_fast_prev = self._ema_fast[slope_index]
        atr_h1 = self._atr[index]
        adx_value = self._adx[index]
        er = self._er[index]
        atr_pct = self._atr_pct[index]

        core = (ema_fast, ema_slow, ema_fast_prev, atr_h1, adx_value, er, atr_pct)
        if not all(is_finite(v) for v in core) or atr_h1 <= 0:
            return RegimeFeatures.invalid()

        normalized_spread = (ema_fast - ema_slow) / atr_h1
        normalized_slope = (ema_fast - ema_fast_prev) / (p.slope_lookback * atr_h1)

        regime = classify(
            adx_value=adx_value,
            normalized_spread=normalized_spread,
            normalized_slope=normalized_slope,
            er=er,
            atr_pct=atr_pct,
            params=p,
        )
        return RegimeFeatures(
            regime=regime,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            atr_h1=atr_h1,
            adx=adx_value,
            er=er,
            atr_pct=atr_pct,
            normalized_spread=normalized_spread,
            normalized_slope=normalized_slope,
        )


def compute_regime_series(bars: Sequence[Bar], params: ResearchParams) -> RegimeSeries:
    """Convenience constructor mirroring the MQL4 side's one-shot warmup."""
    return RegimeSeries(bars, params)
