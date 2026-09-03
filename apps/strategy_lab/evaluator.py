"""Deterministic replay evaluator for the Strategy Lab (INV-8, offline only).

Replays an EMA-cross + ATR stop/take strategy over one-minute bars with an
explicit spread cost. Pure functions — no IO, no sockets, no live state.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from apps.live_supervisor.signals import PriceBar, ScalpParams, ema

__all__ = ["ReplayResult", "replay"]


@dataclass(frozen=True, slots=True)
class ReplayResult:
    trades: int
    wins: int
    total_pnl: Decimal
    gross_profit: Decimal
    gross_loss: Decimal
    profit_factor: Decimal | None
    expectancy: Decimal | None

    @property
    def win_rate(self) -> float:
        return (self.wins / self.trades) if self.trades else 0.0

    def score(self) -> Decimal:
        """Lab ranking score: profit factor weighted by log(trades+1)."""
        if self.trades == 0:
            return Decimal("0")
        pf = self.profit_factor or Decimal("0")
        weight = Decimal(len(str(self.trades)))
        return pf * weight


def _atr_at(bars: Sequence[PriceBar], index: int, period: int) -> Decimal:
    if index < period:
        return Decimal("0")
    ranges = []
    for i in range(index - period + 1, index + 1):
        previous = bars[i - 1]
        current = bars[i]
        ranges.append(max(current.high, previous.close) - min(current.low, previous.close))
    return sum(ranges, start=Decimal("0")) / Decimal(len(ranges))


def replay(
    bars: Sequence[PriceBar],
    params: ScalpParams,
    *,
    stop_ratio: Decimal,
    take_ratio: Decimal,
    spread: Decimal,
) -> ReplayResult:
    """Walk-forward replay: at most one open position at a time."""
    outcomes: list[Decimal] = []
    gross_profit = Decimal("0")
    gross_loss = Decimal("0")
    wins = 0

    side: int | None = None  # +1 long, -1 short
    entry = stop = take = Decimal("0")

    def open_position(direction: int, price: Decimal, atr: Decimal) -> None:
        nonlocal side, entry, stop, take
        side = direction
        entry = price
        distance = atr * stop_ratio
        if direction == 1:
            stop = price - distance
            take = price + atr * take_ratio
        else:
            stop = price + distance
            take = price - atr * take_ratio

    def close_at(exit_price: Decimal) -> None:
        nonlocal side, gross_profit, gross_loss, wins
        pnl = (exit_price - entry) * Decimal(side or 0) - spread
        outcomes.append(pnl)
        if pnl > 0:
            gross_profit += pnl
            wins += 1
        else:
            gross_loss += -pnl
        side = None

    for i, bar in enumerate(bars):
        if side is not None:
            if side == 1:
                if bar.low <= stop:
                    close_at(stop)
                elif bar.high >= take:
                    close_at(take)
            else:
                if bar.high >= stop:
                    close_at(stop)
                elif bar.low <= take:
                    close_at(take)
        if side is None and i >= params.slow_ema:
            window = bars[i - params.slow_ema + 1 : i + 1]
            closes = [b.close for b in window]
            fast = ema(closes, params.fast_ema)
            slow = ema(closes, params.slow_ema)
            if slow <= 0:
                continue
            strength = (fast - slow) / slow
            atr = _atr_at(bars, i, params.atr_period)
            if atr <= 0:
                continue
            if strength >= params.min_strength:
                open_position(1, bar.close, atr)
            elif strength <= -params.min_strength:
                open_position(-1, bar.close, atr)

    if side is not None:
        close_at(bars[-1].close)

    trades = len(outcomes)
    total = sum(outcomes, start=Decimal("0"))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (
        Decimal("0") if gross_profit == 0 else None
    )
    expectancy = (total / Decimal(trades)) if trades else None
    return ReplayResult(
        trades=trades,
        wins=wins,
        total_pnl=total,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=profit_factor,
        expectancy=expectancy,
    )
