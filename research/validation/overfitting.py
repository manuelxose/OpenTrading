"""Multiple-testing and overfitting diagnostics (mandate §36).

Two estimators from the backtest-overfitting literature, plus the bookkeeping that
makes them meaningful:

* **PBO via CSCV** (Bailey, Borwein, López de Prado, Zhu) — split the performance
  matrix into complementary in-sample/out-of-sample combinations and measure how
  often the IS-best configuration lands in the bottom half OOS. A PBO near 0.5 says
  the selection procedure carries no information.
* **Deflated Sharpe Ratio** — corrects an observed Sharpe for the number of trials,
  and for skew and kurtosis. A Sharpe picked as the best of 400 configurations is
  not the same evidence as a Sharpe from a single pre-registered one.

`TrialLedger` records EVERY configuration tried, including the losers. Reporting
only the survivors is the mechanism that makes overfitting invisible (§36: "never
hide unsuccessful parameter runs").
"""

from __future__ import annotations

import itertools
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

__all__ = [
    "TrialLedger",
    "deflated_sharpe_ratio",
    "expected_max_sharpe",
    "probability_of_backtest_overfitting",
]


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _normal_ppf(p: float) -> float:
    """Inverse standard normal CDF (Acklam's rational approximation)."""
    if not 0.0 < p < 1.0:
        raise ValueError("p must be in (0, 1)")
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425

    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
                ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


EULER_MASCHERONI = 0.5772156649015329


def expected_max_sharpe(trials: int, variance_of_sharpes: float) -> float:
    """Expected maximum Sharpe under the null that every trial has zero skill.

    This is the benchmark a "best" Sharpe must beat before it is evidence of
    anything: searching hard enough produces impressive-looking maxima from noise.
    """
    if trials < 2 or variance_of_sharpes <= 0:
        return 0.0
    sigma = math.sqrt(variance_of_sharpes)
    n = float(trials)
    term_a = (1.0 - EULER_MASCHERONI) * _normal_ppf(1.0 - 1.0 / n)
    term_b = EULER_MASCHERONI * _normal_ppf(1.0 - 1.0 / (n * math.e))
    return sigma * (term_a + term_b)


def deflated_sharpe_ratio(
    observed_sharpe: float,
    *,
    trials: int,
    variance_of_sharpes: float,
    sample_length: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> float | None:
    """Probability the observed Sharpe exceeds what selection alone would produce.

    Returns a probability in [0, 1]; values below ~0.95 mean the result is not
    distinguishable from the best of many noisy trials. ``None`` when the inputs
    cannot support the estimate.
    """
    if sample_length < 2:
        return None
    benchmark = expected_max_sharpe(trials, variance_of_sharpes)

    denominator_sq = (
        1.0
        - skewness * observed_sharpe
        + (kurtosis - 1.0) / 4.0 * observed_sharpe ** 2
    )
    if denominator_sq <= 0:
        return None

    numerator = (observed_sharpe - benchmark) * math.sqrt(sample_length - 1)
    return _normal_cdf(numerator / math.sqrt(denominator_sq))


def probability_of_backtest_overfitting(
    performance_matrix: Sequence[Sequence[float]],
    *,
    partitions: int = 8,
) -> dict[str, float] | None:
    """PBO via Combinatorially Symmetric Cross-Validation.

    ``performance_matrix`` is ``[observation][configuration]`` — for example the
    per-window or per-month return of every configuration tried.

    Returns the PBO, the median OOS rank of the IS-best configuration, and the
    fraction of splits where the IS winner lost money OOS. ``None`` when the matrix
    is too small for a meaningful split.
    """
    if not performance_matrix:
        return None
    rows = len(performance_matrix)
    configs = len(performance_matrix[0])
    if configs < 2 or rows < partitions or partitions < 2 or partitions % 2:
        return None

    chunk = rows // partitions
    if chunk < 1:
        return None
    blocks = [
        list(range(i * chunk, (i + 1) * chunk if i < partitions - 1 else rows))
        for i in range(partitions)
    ]

    half = partitions // 2
    logits: list[float] = []
    below_median = 0
    losing_oos = 0
    total = 0

    for combo in itertools.combinations(range(partitions), half):
        is_rows: list[int] = []
        oos_rows: list[int] = []
        for index, block in enumerate(blocks):
            (is_rows if index in combo else oos_rows).extend(block)
        if not is_rows or not oos_rows:
            continue

        is_perf = [
            math.fsum(performance_matrix[r][c] for r in is_rows) for c in range(configs)
        ]
        oos_perf = [
            math.fsum(performance_matrix[r][c] for r in oos_rows) for c in range(configs)
        ]

        best = max(range(configs), key=lambda c: is_perf[c])
        # Rank of the IS winner within the OOS ordering (1 = worst).
        ordered = sorted(range(configs), key=lambda c: oos_perf[c])
        rank = ordered.index(best) + 1
        relative = rank / (configs + 1.0)

        total += 1
        if relative <= 0.5:
            below_median += 1
        if oos_perf[best] < 0:
            losing_oos += 1

        clamped = min(max(relative, 1e-6), 1 - 1e-6)
        logits.append(math.log(clamped / (1 - clamped)))

    if not total:
        return None

    return {
        "pbo": below_median / total,
        "splits": float(total),
        "median_logit": sorted(logits)[len(logits) // 2] if logits else 0.0,
        "fraction_is_winner_loses_oos": losing_oos / total,
        "configurations": float(configs),
    }


@dataclass(slots=True)
class TrialLedger:
    """Records EVERY configuration tried, including the failures (mandate §36).

    The trial count is an input to the Deflated Sharpe Ratio, so under-recording
    trials directly inflates the apparent significance of the result.
    """

    path: Path
    trials: list[dict[str, object]] = field(default_factory=list)

    def record(
        self,
        *,
        config_hash: str,
        params: dict[str, float],
        profit_factor: float | None,
        sharpe: float | None,
        net_return_pct: float,
        trades: int,
        partition: str,
    ) -> None:
        self.trials.append(
            {
                "recorded_at": datetime.now().isoformat(timespec="seconds"),
                "config_hash": config_hash,
                "params": params,
                "profit_factor": profit_factor,
                "sharpe": sharpe,
                "net_return_pct": net_return_pct,
                "trades": trades,
                "partition": partition,
            }
        )

    @property
    def count(self) -> int:
        return len(self.trials)

    def sharpe_variance(self) -> float:
        values = [
            float(t["sharpe"]) for t in self.trials if t["sharpe"] is not None
        ]
        if len(values) < 2:
            return 0.0
        mean = math.fsum(values) / len(values)
        return math.fsum((v - mean) ** 2 for v in values) / (len(values) - 1)

    def flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.trials, indent=1), encoding="utf-8")

    def summary(self) -> str:
        if not self.trials:
            return "no trials recorded"
        pfs = [t["profit_factor"] for t in self.trials if t["profit_factor"] is not None]
        best = max(pfs) if pfs else None
        median = sorted(pfs)[len(pfs) // 2] if pfs else None
        return "\n".join(
            [
                f"trials recorded        : {self.count}",
                f"best profit factor     : {'n/a' if best is None else f'{best:.3f}'}",
                f"median profit factor   : {'n/a' if median is None else f'{median:.3f}'}",
                f"variance of Sharpes    : {self.sharpe_variance():.5f}",
                "",
                "The trial count feeds the Deflated Sharpe Ratio. Under-recording it",
                "inflates the apparent significance of whatever survived.",
            ]
        )
