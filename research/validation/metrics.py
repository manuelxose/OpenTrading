"""Performance metrics (mandate §42) and attribution (§39, §40).

Every metric here is computed from a realized trade list and an equity curve — no
metric is estimated, annualized from a guess, or carried over from a source
document. Where a metric is undefined (no losses, no trades, a degenerate series)
the result is ``None`` rather than a flattering substitute.

Nothing in this module is evidence by itself. A metric is only meaningful next to
the data version, config hash and cost model that produced it.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from research.strategies.xau_rpb.types import Direction, Trade

__all__ = [
    "PerformanceMetrics",
    "compute_metrics",
    "drawdown_series",
    "max_drawdown",
    "yearly_breakdown",
]

TRADING_DAYS = 252.0
BARS_PER_DAY_M15 = 96.0


@dataclass(slots=True)
class PerformanceMetrics:
    """The full §42 metric set. ``None`` means "undefined", never "zero"."""

    trades: int = 0
    wins: int = 0
    losses: int = 0
    net_profit: float = 0.0
    net_return_pct: float = 0.0
    cagr_pct: float | None = None
    profit_factor: float | None = None
    expectancy: float = 0.0
    expectancy_r: float = 0.0
    sharpe: float | None = None
    sortino: float | None = None
    max_drawdown_pct: float = 0.0
    max_drawdown_abs: float = 0.0
    recovery_factor: float | None = None
    calmar: float | None = None
    win_rate: float = 0.0
    average_win: float = 0.0
    average_loss: float = 0.0
    payoff_ratio: float | None = None
    average_holding_bars: float = 0.0
    max_losing_streak: int = 0
    max_winning_streak: int = 0
    average_mae: float = 0.0
    average_mfe: float = 0.0
    exposure_pct: float = 0.0
    total_costs: float = 0.0
    initial_equity: float = 0.0
    final_equity: float = 0.0
    start: datetime | None = None
    end: datetime | None = None
    largest_win: float = 0.0
    largest_loss: float = 0.0
    top5_profit_share: float | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "trades": self.trades,
            "wins": self.wins,
            "losses": self.losses,
            "net_profit": round(self.net_profit, 2),
            "net_return_pct": round(self.net_return_pct, 3),
            "cagr_pct": None if self.cagr_pct is None else round(self.cagr_pct, 3),
            "profit_factor": (
                None if self.profit_factor is None else round(self.profit_factor, 4)
            ),
            "expectancy": round(self.expectancy, 4),
            "expectancy_r": round(self.expectancy_r, 4),
            "sharpe": None if self.sharpe is None else round(self.sharpe, 4),
            "sortino": None if self.sortino is None else round(self.sortino, 4),
            "max_drawdown_pct": round(self.max_drawdown_pct, 3),
            "recovery_factor": (
                None if self.recovery_factor is None else round(self.recovery_factor, 4)
            ),
            "calmar": None if self.calmar is None else round(self.calmar, 4),
            "win_rate": round(self.win_rate, 4),
            "average_win": round(self.average_win, 2),
            "average_loss": round(self.average_loss, 2),
            "payoff_ratio": (
                None if self.payoff_ratio is None else round(self.payoff_ratio, 4)
            ),
            "average_holding_bars": round(self.average_holding_bars, 2),
            "max_losing_streak": self.max_losing_streak,
            "max_winning_streak": self.max_winning_streak,
            "exposure_pct": round(self.exposure_pct, 3),
            "total_costs": round(self.total_costs, 2),
            "top5_profit_share": (
                None if self.top5_profit_share is None else round(self.top5_profit_share, 4)
            ),
        }


def drawdown_series(equity: Sequence[float]) -> list[float]:
    """Percentage drawdown from the running peak, per observation."""
    out: list[float] = []
    peak = -math.inf
    for value in equity:
        peak = max(peak, value)
        out.append(0.0 if peak <= 0 else (peak - value) / peak * 100.0)
    return out


def max_drawdown(equity: Sequence[float]) -> tuple[float, float]:
    """Return ``(max_drawdown_pct, max_drawdown_abs)``."""
    peak = -math.inf
    worst_pct = 0.0
    worst_abs = 0.0
    for value in equity:
        peak = max(peak, value)
        if peak > 0:
            worst_pct = max(worst_pct, (peak - value) / peak * 100.0)
        worst_abs = max(worst_abs, peak - value)
    return worst_pct, worst_abs


def _streaks(trades: Sequence[Trade]) -> tuple[int, int]:
    longest_loss = longest_win = 0
    current_loss = current_win = 0
    for trade in trades:
        if trade.pnl > 0:
            current_win += 1
            current_loss = 0
        elif trade.pnl < 0:
            current_loss += 1
            current_win = 0
        else:
            current_win = current_loss = 0
        longest_win = max(longest_win, current_win)
        longest_loss = max(longest_loss, current_loss)
    return longest_loss, longest_win


def _sharpe_sortino(returns: Sequence[float], periods_per_year: float) -> tuple[
    float | None, float | None
]:
    """Annualized Sharpe and Sortino from per-observation returns."""
    n = len(returns)
    if n < 2:
        return None, None
    mean = math.fsum(returns) / n
    variance = math.fsum((r - mean) ** 2 for r in returns) / (n - 1)
    std = math.sqrt(variance)
    sharpe = None if std <= 0 else mean / std * math.sqrt(periods_per_year)

    downside = [r for r in returns if r < 0]
    if not downside:
        return sharpe, None
    downside_var = math.fsum(r * r for r in downside) / len(downside)
    downside_std = math.sqrt(downside_var)
    sortino = None if downside_std <= 0 else mean / downside_std * math.sqrt(periods_per_year)
    return sharpe, sortino


def compute_metrics(
    trades: Sequence[Trade],
    equity_curve: Sequence[tuple[datetime, float]],
    initial_equity: float,
    *,
    bars_per_year: float = TRADING_DAYS * BARS_PER_DAY_M15,
) -> PerformanceMetrics:
    """Compute the full metric set from realized trades and the equity curve."""
    m = PerformanceMetrics(initial_equity=initial_equity)
    m.trades = len(trades)
    if equity_curve:
        m.start = equity_curve[0][0]
        m.end = equity_curve[-1][0]
        m.final_equity = equity_curve[-1][1]
    else:
        m.final_equity = initial_equity

    equity_values = [value for _, value in equity_curve] or [initial_equity]
    m.max_drawdown_pct, m.max_drawdown_abs = max_drawdown(equity_values)

    if m.trades == 0:
        return m

    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl < 0]
    m.wins, m.losses = len(wins), len(losses)
    m.win_rate = m.wins / m.trades

    gross_profit = math.fsum(t.pnl for t in wins)
    gross_loss = abs(math.fsum(t.pnl for t in losses))
    m.net_profit = gross_profit - gross_loss
    m.net_return_pct = (
        m.net_profit / initial_equity * 100.0 if initial_equity > 0 else 0.0
    )
    # Undefined rather than infinite when there are no losses at all.
    m.profit_factor = None if gross_loss == 0 else gross_profit / gross_loss

    m.expectancy = m.net_profit / m.trades
    m.expectancy_r = math.fsum(t.r_multiple for t in trades) / m.trades
    m.average_win = gross_profit / m.wins if m.wins else 0.0
    m.average_loss = gross_loss / m.losses if m.losses else 0.0
    m.payoff_ratio = (
        None if m.average_loss == 0 else m.average_win / m.average_loss
    )
    m.largest_win = max((t.pnl for t in trades), default=0.0)
    m.largest_loss = min((t.pnl for t in trades), default=0.0)

    # Concentration check (§44): do a handful of trades explain the result?
    if m.net_profit > 0:
        top5 = sorted((t.pnl for t in trades), reverse=True)[:5]
        m.top5_profit_share = math.fsum(top5) / m.net_profit

    m.average_holding_bars = math.fsum(t.bars_held for t in trades) / m.trades
    m.average_mae = math.fsum(t.mae for t in trades) / m.trades
    m.average_mfe = math.fsum(t.mfe for t in trades) / m.trades
    m.total_costs = math.fsum(t.costs for t in trades)
    m.max_losing_streak, m.max_winning_streak = _streaks(trades)

    if len(equity_values) > 1:
        bars_held = math.fsum(t.bars_held for t in trades)
        m.exposure_pct = min(100.0, bars_held / len(equity_values) * 100.0)
        returns = [
            (equity_values[i] - equity_values[i - 1]) / equity_values[i - 1]
            for i in range(1, len(equity_values))
            if equity_values[i - 1] > 0
        ]
        m.sharpe, m.sortino = _sharpe_sortino(returns, bars_per_year)

    if m.start and m.end and initial_equity > 0 and m.final_equity > 0:
        years = (m.end - m.start).days / 365.25
        if years > 0.25:  # a CAGR over a sub-quarter sample is noise, not a rate
            m.cagr_pct = ((m.final_equity / initial_equity) ** (1.0 / years) - 1.0) * 100.0
            if m.max_drawdown_pct > 0:
                m.calmar = m.cagr_pct / m.max_drawdown_pct

    if m.max_drawdown_abs > 0:
        m.recovery_factor = m.net_profit / m.max_drawdown_abs

    return m


@dataclass(slots=True)
class SideBreakdown:
    """Long / short / combined attribution (mandate §39)."""

    long: PerformanceMetrics
    short: PerformanceMetrics
    combined: PerformanceMetrics


def side_breakdown(
    trades: Sequence[Trade],
    equity_curve: Sequence[tuple[datetime, float]],
    initial_equity: float,
) -> SideBreakdown:
    """Report each side separately: a combined curve can hide a broken side."""
    longs = [t for t in trades if t.direction is Direction.LONG]
    shorts = [t for t in trades if t.direction is Direction.SHORT]
    return SideBreakdown(
        long=compute_metrics(longs, equity_curve, initial_equity),
        short=compute_metrics(shorts, equity_curve, initial_equity),
        combined=compute_metrics(trades, equity_curve, initial_equity),
    )


@dataclass(slots=True)
class YearStats:
    year: int
    trades: int
    net_profit: float
    win_rate: float
    profit_factor: float | None = None
    contribution_pct: float = 0.0


def yearly_breakdown(trades: Sequence[Trade]) -> list[YearStats]:
    """Per-year attribution, with each year's share of total profit (mandate §40)."""
    buckets: dict[int, list[Trade]] = {}
    for trade in trades:
        buckets.setdefault(trade.entry_time.year, []).append(trade)

    total = math.fsum(t.pnl for t in trades)
    out: list[YearStats] = []
    for year in sorted(buckets):
        group = buckets[year]
        gross_profit = math.fsum(t.pnl for t in group if t.pnl > 0)
        gross_loss = abs(math.fsum(t.pnl for t in group if t.pnl < 0))
        net = math.fsum(t.pnl for t in group)
        wins = sum(1 for t in group if t.pnl > 0)
        out.append(
            YearStats(
                year=year,
                trades=len(group),
                net_profit=net,
                win_rate=wins / len(group) if group else 0.0,
                profit_factor=None if gross_loss == 0 else gross_profit / gross_loss,
                contribution_pct=(net / total * 100.0) if total != 0 else 0.0,
            )
        )
    return out


@dataclass(slots=True)
class GroupStats:
    """Generic attribution bucket used for session and regime breakdowns."""

    label: str
    trades: int
    net_profit: float
    win_rate: float
    expectancy_r: float
    contribution_pct: float = 0.0
    extra: dict[str, float] = field(default_factory=dict)


def group_by(trades: Sequence[Trade], key: str) -> list[GroupStats]:
    """Attribution by a trade attribute (``regime_at_entry``, ``exit_reason``, ...)."""
    buckets: dict[str, list[Trade]] = {}
    for trade in trades:
        value = getattr(trade, key, None)
        label = getattr(value, "value", str(value))
        buckets.setdefault(label, []).append(trade)

    total = math.fsum(t.pnl for t in trades)
    out: list[GroupStats] = []
    for label in sorted(buckets):
        group = buckets[label]
        net = math.fsum(t.pnl for t in group)
        wins = sum(1 for t in group if t.pnl > 0)
        out.append(
            GroupStats(
                label=label,
                trades=len(group),
                net_profit=net,
                win_rate=wins / len(group),
                expectancy_r=math.fsum(t.r_multiple for t in group) / len(group),
                contribution_pct=(net / total * 100.0) if total != 0 else 0.0,
            )
        )
    return out
