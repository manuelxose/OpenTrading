"""Deterministic baseline momentum (EMA cross) on broker quotes — INV-1.

No ML, no LLM, no external model: the signal is a fixed EMA(12)/EMA(45)
momentum score over one-minute bars built exclusively from broker quotes.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Sequence

from core.domain.enums import SignalDirection

__all__ = [
    "BaselineSignal",
    "EMA_FAST",
    "EMA_SLOW",
    "MIN_BARS",
    "MinuteBarSeries",
    "ScalpParams",
    "momentum_signal",
    "scalp_signal",
]

EMA_FAST = 12
EMA_SLOW = 45
ATR_PERIOD = 14
MIN_BARS = EMA_SLOW + ATR_PERIOD


@dataclass(frozen=True, slots=True)
class PriceBar:
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    closed_at: datetime


@dataclass(frozen=True, slots=True)
class ScalpParams:
    """Versionable EMA-cross strategy parameters (Strategy Lab evaluates
    candidates over this space; live deployments pin one frozen set)."""

    fast_ema: int = EMA_FAST
    slow_ema: int = EMA_SLOW
    atr_period: int = ATR_PERIOD
    min_strength: Decimal = Decimal("0.0002")

    @property
    def warmup_bars(self) -> int:
        return self.slow_ema + self.atr_period + 2


@dataclass(frozen=True, slots=True)
class BaselineSignal:
    direction: SignalDirection
    strength: Decimal
    atr: Decimal

    @property
    def tradable(self) -> bool:
        return self.direction is not SignalDirection.FLAT


def ema(values: Sequence[Decimal], period: int) -> Decimal:
    """Exponential moving average over a sequence (deterministic)."""
    if not values:
        raise ValueError("ema requires at least one value")
    k = Decimal(2) / Decimal(period + 1)
    result = Decimal(values[0])
    for value in values[1:]:
        result = value * k + result * (Decimal(1) - k)
    return result


class MinuteBarSeries:
    """Aggregates broker ticks into one-minute bars (bounded memory)."""

    def __init__(self, max_bars: int = 400) -> None:
        self._max_bars = max_bars
        self._closed: deque[PriceBar] = deque(maxlen=max_bars)
        self._current_minute: datetime | None = None
        self._open = self._high = self._low = self._close = Decimal("0")

    def on_price(self, mid: Decimal, observed_at: datetime) -> None:
        minute = observed_at.replace(second=0, microsecond=0)
        if self._current_minute is None:
            self._current_minute = minute
            self._open = self._high = self._low = self._close = mid
            return
        if minute > self._current_minute:
            self._closed.append(
                PriceBar(
                    open=self._open,
                    high=self._high,
                    low=self._low,
                    close=self._close,
                    closed_at=self._current_minute,
                )
            )
            self._current_minute = minute
            self._open = self._high = self._low = self._close = mid
            return
        if mid > self._high:
            self._high = mid
        if mid < self._low:
            self._low = mid
        self._close = mid

    def bars(self) -> tuple[PriceBar, ...]:
        return tuple(self._closed)

    def closes(self) -> tuple[Decimal, ...]:
        return tuple(bar.close for bar in self._closed)

    def atr(self, period: int = ATR_PERIOD) -> Decimal | None:
        bars = self.bars()
        if len(bars) < period + 1:
            return None
        ranges: list[Decimal] = []
        for i in range(1, len(bars)):
            previous = bars[i - 1]
            current = bars[i]
            ranges.append(max(current.high, previous.close) - min(current.low, previous.close))
        window = ranges[-period:]
        return sum(window, start=Decimal("0")) / Decimal(len(window))


def momentum_signal(series: MinuteBarSeries, min_strength: Decimal) -> BaselineSignal:
    """EMA(12) vs EMA(45) momentum score; FLAT below ``min_strength``."""
    return scalp_signal(series, ScalpParams(min_strength=min_strength))


def scalp_signal(series: MinuteBarSeries, params: ScalpParams) -> BaselineSignal:
    """Parameterized EMA momentum score; FLAT below ``params.min_strength``."""
    closes = series.closes()
    atr = series.atr(params.atr_period) or Decimal("0")
    if len(closes) < params.slow_ema:
        return BaselineSignal(SignalDirection.FLAT, Decimal("0"), atr)
    fast = ema(closes[-params.slow_ema:], params.fast_ema)
    slow = ema(closes[-params.slow_ema:], params.slow_ema)
    if slow <= 0:
        return BaselineSignal(SignalDirection.FLAT, Decimal("0"), atr)
    strength = (fast - slow) / slow
    if strength >= params.min_strength:
        return BaselineSignal(SignalDirection.LONG, strength, atr)
    if strength <= -params.min_strength:
        return BaselineSignal(SignalDirection.SHORT, strength, atr)
    return BaselineSignal(SignalDirection.FLAT, strength, atr)


def floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step
