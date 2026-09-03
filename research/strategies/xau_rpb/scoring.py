"""Signal score (spec §6).

Seven interpretable factors, maximum 9 points. Deliberately small: a 20-indicator
scoring engine would add parameter surface without adding independent information,
which is the overfitting mechanism the audit warns about.

The score can only make an otherwise valid setup *ineligible*. It can never
substitute for the two hard gates — regime (§4.2) and confirmed breakout (§5.4) —
which are enforced before scoring is ever reached.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import ResearchParams
from .types import Direction, Regime

__all__ = ["MAX_SCORE", "ScoreBreakdown", "compute_score"]

MAX_SCORE = 9


@dataclass(frozen=True, slots=True)
class ScoreBreakdown:
    """Per-factor attribution, logged verbatim so a score is always explainable."""

    regime_confirmed: int
    slope_ok: int
    depth_ok: int
    breakout_confirmed: int
    atr_regime_ok: int
    session_ok: int
    spread_ok: int

    @property
    def total(self) -> int:
        return (
            self.regime_confirmed
            + self.slope_ok
            + self.depth_ok
            + self.breakout_confirmed
            + self.atr_regime_ok
            + self.session_ok
            + self.spread_ok
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "regime_confirmed": self.regime_confirmed,
            "slope_ok": self.slope_ok,
            "depth_ok": self.depth_ok,
            "breakout_confirmed": self.breakout_confirmed,
            "atr_regime_ok": self.atr_regime_ok,
            "session_ok": self.session_ok,
            "spread_ok": self.spread_ok,
            "total": self.total,
        }


def compute_score(
    *,
    regime: Regime,
    direction: Direction,
    normalized_slope: float,
    atr_pct: float,
    depth_atr: float,
    breakout_confirmed: bool,
    session_permitted: bool,
    spread_points: float,
    atr_m15: float,
    params: ResearchParams,
    spread_atr_max: float,
    spread_abs_max_points: float,
    point: float,
) -> ScoreBreakdown:
    """Evaluate the seven factors of spec §6."""
    expected = Regime.TREND_UP if direction is Direction.LONG else Regime.TREND_DOWN
    regime_pts = 2 if regime is expected else 0

    slope_pts = 1 if abs(normalized_slope) >= params.score_slope_min else 0

    depth_pts = (
        1
        if params.min_pullback_depth_atr <= depth_atr <= params.max_pullback_depth_atr
        else 0
    )

    breakout_pts = 2 if breakout_confirmed else 0

    atr_pts = 1 if params.atr_pct_floor <= atr_pct < params.atr_pct_high else 0

    session_pts = 1 if session_permitted else 0

    # The spread test is relative (to volatility) AND absolute: a fixed number
    # alone is insufficient, and a purely relative one lets a volatility spike
    # justify an arbitrarily wide spread.
    spread_price = spread_points * point
    spread_pts = (
        1
        if spread_price <= spread_atr_max * atr_m15 and spread_points <= spread_abs_max_points
        else 0
    )

    return ScoreBreakdown(
        regime_confirmed=regime_pts,
        slope_ok=slope_pts,
        depth_ok=depth_pts,
        breakout_confirmed=breakout_pts,
        atr_regime_ok=atr_pts,
        session_ok=session_pts,
        spread_ok=spread_pts,
    )
