"""Indicators, defined exactly as in spec §3.1.

Deliberately pure Python over plain lists rather than a vectorized library:

* the arithmetic is the same operation order the MQL4 mirror performs, which is
  what makes the signal-parity tests (spec §5 of the validation methodology)
  meaningful rather than approximate;
* no library default (seeding, smoothing choice) can silently change results
  between versions.

Every series is returned aligned to the input, with ``nan`` in positions where the
indicator is not yet defined. Callers must treat ``nan`` as INSUFFICIENT_HISTORY
and fail closed (spec §15) — never as zero.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from .types import Bar

__all__ = [
    "adx",
    "atr",
    "atr_percentile",
    "efficiency_ratio",
    "ema",
    "is_finite",
    "true_range",
    "wilder_rma",
]

NAN = float("nan")


def is_finite(value: float) -> bool:
    """True only for a real, usable number (spec §15 fails closed on anything else)."""
    return not (math.isnan(value) or math.isinf(value))


def ema(values: Sequence[float], period: int) -> list[float]:
    """EMA with ``alpha = 2/(n+1)``, seeded with the SMA of the first ``period`` values."""
    if period < 1:
        raise ValueError("period must be >= 1")
    out = [NAN] * len(values)
    if len(values) < period:
        return out
    alpha = 2.0 / (period + 1.0)
    seed = math.fsum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * alpha + prev * (1.0 - alpha)
        out[i] = prev
    return out


def true_range(bars: Sequence[Bar]) -> list[float]:
    """TR series; index 0 is ``nan`` because TR needs the previous close."""
    out = [NAN] * len(bars)
    for i in range(1, len(bars)):
        prev_close = bars[i - 1].close
        out[i] = max(
            bars[i].high - bars[i].low,
            abs(bars[i].high - prev_close),
            abs(bars[i].low - prev_close),
        )
    return out


def wilder_rma(values: Sequence[float], period: int, start: int) -> list[float]:
    """Wilder's smoothing, seeded with the SMA of ``period`` values from ``start``.

    ``start`` is the first index at which ``values`` is defined, so the seed lands
    at ``start + period - 1`` and never consumes a ``nan``.
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    out = [NAN] * len(values)
    seed_end = start + period
    if len(values) < seed_end:
        return out
    seed = math.fsum(values[start:seed_end]) / period
    out[seed_end - 1] = seed
    prev = seed
    for i in range(seed_end, len(values)):
        prev = (prev * (period - 1) + values[i]) / period
        out[i] = prev
    return out


def atr(bars: Sequence[Bar], period: int) -> list[float]:
    """Average True Range (Wilder). First defined value sits at index ``period``."""
    return wilder_rma(true_range(bars), period, start=1)


def adx(bars: Sequence[Bar], period: int) -> list[float]:
    """Wilder ADX. First defined value sits at index ``2*period - 1``."""
    n = len(bars)
    out = [NAN] * n
    if n < 2:
        return out

    plus_dm = [NAN] * n
    minus_dm = [NAN] * n
    for i in range(1, n):
        up = bars[i].high - bars[i - 1].high
        down = bars[i - 1].low - bars[i].low
        plus_dm[i] = up if (up > down and up > 0) else 0.0
        minus_dm[i] = down if (down > up and down > 0) else 0.0

    tr = true_range(bars)
    sm_plus = wilder_rma(plus_dm, period, start=1)
    sm_minus = wilder_rma(minus_dm, period, start=1)
    sm_tr = wilder_rma(tr, period, start=1)

    dx = [NAN] * n
    first_dx = -1
    for i in range(n):
        if math.isnan(sm_tr[i]) or sm_tr[i] <= 0:
            continue
        plus_di = 100.0 * sm_plus[i] / sm_tr[i]
        minus_di = 100.0 * sm_minus[i] / sm_tr[i]
        denom = plus_di + minus_di
        dx[i] = 0.0 if denom == 0 else 100.0 * abs(plus_di - minus_di) / denom
        if first_dx < 0:
            first_dx = i

    if first_dx < 0:
        return out
    return wilder_rma(dx, period, start=first_dx)


def efficiency_ratio(closes: Sequence[float], window: int) -> list[float]:
    """Kaufman Efficiency Ratio: net displacement over total path length."""
    if window < 1:
        raise ValueError("window must be >= 1")
    n = len(closes)
    out = [NAN] * n
    for i in range(window, n):
        net = abs(closes[i] - closes[i - window])
        path = math.fsum(abs(closes[j] - closes[j - 1]) for j in range(i - window + 1, i + 1))
        out[i] = 0.0 if path == 0 else net / path
    return out


def atr_percentile(atr_series: Sequence[float], window: int) -> list[float]:
    """Fraction of the trailing ``window`` ATR values STRICTLY below the current one.

    Ties count as "not less than" (spec §3.1), which keeps the statistic monotone
    and identical between the Python and MQL4 implementations.
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    n = len(atr_series)
    out = [NAN] * n
    for i in range(n):
        current = atr_series[i]
        if math.isnan(current):
            continue
        lo = i - window + 1
        if lo < 0:
            continue
        sample = atr_series[lo : i + 1]
        if any(math.isnan(v) for v in sample):
            continue
        below = sum(1 for v in sample if v < current)
        out[i] = below / float(window)
    return out
