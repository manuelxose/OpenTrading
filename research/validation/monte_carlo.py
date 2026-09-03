"""Monte Carlo robustness families (mandate §37).

Four families, each answering a different question:

* **Trade-sequence bootstrap** — "was the observed drawdown lucky ordering?"
* **Block bootstrap** — the same, while preserving local clustering, because
  losing trades in a trend system arrive together and IID resampling destroys
  exactly the property that hurts.
* **Execution perturbation** — "does the edge survive worse fills?" This one is
  run by re-executing the strategy, not by rescaling P&L, because a wider spread
  changes which trades are taken, not merely what they earn.
* **Parameter jitter** — "is this a plateau or a spike?"

The percentile convention is stated once and used everywhere: nearest-rank on the
sorted sample, so P95 is a value that actually occurred.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass, field

from research.strategies.xau_rpb.types import Trade

from .metrics import max_drawdown

__all__ = [
    "MonteCarloResult",
    "block_bootstrap",
    "percentile",
    "sequence_bootstrap",
]


def percentile(values: Sequence[float], q: float) -> float:
    """Nearest-rank percentile: the returned value is one that actually occurred."""
    if not values:
        raise ValueError("percentile of an empty sample is undefined")
    if not 0.0 <= q <= 1.0:
        raise ValueError("q must be within [0, 1]")
    ordered = sorted(values)
    rank = max(1, math.ceil(q * len(ordered)))
    return ordered[rank - 1]


@dataclass(slots=True)
class MonteCarloResult:
    """Distributional summary of a resampling family."""

    family: str
    iterations: int
    drawdowns: list[float] = field(default_factory=list)
    final_returns: list[float] = field(default_factory=list)
    losing_streaks: list[int] = field(default_factory=list)
    ruin_count: int = 0

    @property
    def p50_drawdown(self) -> float:
        return percentile(self.drawdowns, 0.50)

    @property
    def p95_drawdown(self) -> float:
        return percentile(self.drawdowns, 0.95)

    @property
    def p99_drawdown(self) -> float:
        return percentile(self.drawdowns, 0.99)

    @property
    def worst_drawdown(self) -> float:
        return max(self.drawdowns)

    @property
    def median_return(self) -> float:
        return percentile(self.final_returns, 0.50)

    @property
    def p05_return(self) -> float:
        return percentile(self.final_returns, 0.05)

    @property
    def probability_of_loss(self) -> float:
        if not self.final_returns:
            return 0.0
        return sum(1 for r in self.final_returns if r < 0) / len(self.final_returns)

    @property
    def risk_of_ruin(self) -> float:
        return self.ruin_count / self.iterations if self.iterations else 0.0

    @property
    def max_losing_streak_p95(self) -> int:
        return int(percentile([float(s) for s in self.losing_streaks], 0.95))

    def summary(self) -> str:
        return "\n".join(
            [
                f"family                 : {self.family}",
                f"iterations             : {self.iterations}",
                f"median drawdown %      : {self.p50_drawdown:.2f}",
                f"P95 drawdown %         : {self.p95_drawdown:.2f}",
                f"P99 drawdown %         : {self.p99_drawdown:.2f}",
                f"worst drawdown %       : {self.worst_drawdown:.2f}",
                f"median return %        : {self.median_return:.2f}",
                f"P05 return %           : {self.p05_return:.2f}",
                f"probability of loss    : {self.probability_of_loss:.3f}",
                f"risk of ruin           : {self.risk_of_ruin:.4f}",
                f"P95 losing streak      : {self.max_losing_streak_p95}",
            ]
        )


def _simulate(
    pnls: Sequence[float], initial_equity: float, ruin_threshold_pct: float
) -> tuple[float, float, int, bool]:
    """Replay a P&L ordering and return (drawdown%, return%, longest losing run, ruined)."""
    equity = initial_equity
    curve = [equity]
    streak = longest = 0
    ruined = False
    ruin_level = initial_equity * (1.0 - ruin_threshold_pct / 100.0)

    for pnl in pnls:
        equity += pnl
        curve.append(equity)
        if pnl < 0:
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 0
        if equity <= ruin_level:
            ruined = True

    dd_pct, _ = max_drawdown(curve)
    total_return = (equity - initial_equity) / initial_equity * 100.0
    return dd_pct, total_return, longest, ruined


def sequence_bootstrap(
    trades: Sequence[Trade],
    *,
    initial_equity: float = 100_000.0,
    iterations: int = 2000,
    seed: int = 20260831,
    ruin_threshold_pct: float = 50.0,
) -> MonteCarloResult:
    """Resample the trade ORDER with replacement (mandate §37 family 1).

    Answers: how much of the observed drawdown was the particular sequence, rather
    than the distribution of outcomes?
    """
    result = MonteCarloResult(family="trade_sequence_bootstrap", iterations=0)
    pnls = [t.pnl for t in trades]
    if not pnls:
        return result

    rng = random.Random(seed)
    for _ in range(iterations):
        sample = [pnls[rng.randrange(len(pnls))] for _ in range(len(pnls))]
        dd, ret, streak, ruined = _simulate(sample, initial_equity, ruin_threshold_pct)
        result.drawdowns.append(dd)
        result.final_returns.append(ret)
        result.losing_streaks.append(streak)
        result.ruin_count += int(ruined)
    result.iterations = iterations
    return result


def block_bootstrap(
    trades: Sequence[Trade],
    *,
    block_size: int = 10,
    initial_equity: float = 100_000.0,
    iterations: int = 2000,
    seed: int = 20260831,
    ruin_threshold_pct: float = 50.0,
) -> MonteCarloResult:
    """Resample contiguous BLOCKS of trades (mandate §37 family 2).

    IID resampling destroys the clustering that actually produces the painful
    drawdowns in a trend-following system. Blocks preserve some of it, so the
    tail this family reports is usually the more honest one.
    """
    result = MonteCarloResult(family=f"block_bootstrap(size={block_size})", iterations=0)
    pnls = [t.pnl for t in trades]
    if not pnls or block_size < 1:
        return result

    rng = random.Random(seed)
    n = len(pnls)
    blocks_needed = math.ceil(n / block_size)

    for _ in range(iterations):
        sample: list[float] = []
        for _ in range(blocks_needed):
            start = rng.randrange(n)
            for offset in range(block_size):
                sample.append(pnls[(start + offset) % n])
        sample = sample[:n]
        dd, ret, streak, ruined = _simulate(sample, initial_equity, ruin_threshold_pct)
        result.drawdowns.append(dd)
        result.final_returns.append(ret)
        result.losing_streaks.append(streak)
        result.ruin_count += int(ruined)
    result.iterations = iterations
    return result
