"""Deterministic per-trade metrics (architecture §17).

Pure functions — no IO, no clocks, no risk-limit writes. The same code path
serves PAPER today and LIVE later (INV-4 discipline: the learning loop is
read-only over risk state).

Metric definitions
------------------
- ``pnl_gross`` / ``pnl_net`` — realized PnL before / after fees, signed, in
  the account currency;
- ``fees`` — total costs carried on the outcome;
- ``slippage`` — accumulated slippage carried on the outcome (0 when the venue
  did not report it);
- ``r_multiple`` — ``pnl_net / risk_amount`` using the Risk-Engine-approved
  risk amount; ``None`` when no risk amount is known (never invented);
- ``actual_return_pct`` — signed move over entry:
  ``sign x (exit - entry) / entry x 100``;
- ``alpha_pct`` — excess return: ``actual - benchmark`` when a benchmark return
  is supplied, otherwise ``actual - expected`` (plan-relative alpha);
- ``mae_pct`` / ``mfe_pct`` — maximum adverse / favorable excursion over the
  observed price path between open and close, as a percentage of entry; the
  loop never fabricates excursion data, so an empty path yields ``None``;
- ``holding_seconds`` — wall-clock time between open and close;
- ``entry_efficiency`` — ``(exit - entry) / (best - entry)``: the fraction of
  the favorable extreme captured at exit (negative for losers);
- ``exit_efficiency`` — ``(exit - worst) / (best - worst)`` clamped to
  ``[0, 1]``: where the exit landed in the adverse→favorable range;
- ``prediction_error_pct`` — ``|actual - predicted|`` in return-percent;
- ``signal_calibration_error`` — per-producer Brier error
  ``(confidence - hit)²`` (see :func:`brier_error`), aggregated by the analysis
  engine;
- ``market_regime`` — the regime label captured at entry (``unknown`` when no
  classifier ran).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from core.domain.enums import SignalDirection
from core.schemas import TradeOutcome
from core.schemas.posttrade import TradeMetrics
from pydantic import BaseModel, Field

__all__ = [
    "MetricsInput",
    "PricePoint",
    "brier_error",
    "compute_trade_metrics",
    "direction_correct",
    "signed_return_pct",
]


class PricePoint(BaseModel):
    """One observed price observation between open and close."""

    model_config = {"frozen": True, "extra": "forbid"}

    ts: datetime
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)


@dataclass(frozen=True)
class MetricsInput:
    """Everything the metric computation reads (pure inputs, no IO)."""

    outcome: TradeOutcome
    risk_amount: Decimal | None = None
    expected_return_pct: float | None = None
    benchmark_return_pct: float | None = None
    path: tuple[PricePoint, ...] = ()
    regime: str | None = None
    signal_calibration_error: dict[str, float] | None = None
    planned_stop: Decimal | None = None
    planned_take: Decimal | None = None


def signed_return_pct(entry: Decimal, exit_price: Decimal, direction: SignalDirection) -> float:
    """Signed move over entry in percent (LONG: up positive; SHORT: down positive)."""
    if entry <= 0:
        raise ValueError("entry price must be positive")
    sign = Decimal("1") if direction is SignalDirection.LONG else Decimal("-1")
    return float(sign * (exit_price - entry) / entry * 100)


def direction_correct(direction: SignalDirection | None, realized_move_up: bool) -> bool | None:
    """A producer's stance vs the realized move.

    LONG is correct when the market rose, SHORT when it fell; FLAT/absent
    stances are never direction-correct (they contributed no directional view).
    """
    if direction is SignalDirection.LONG:
        return realized_move_up
    if direction is SignalDirection.SHORT:
        return not realized_move_up
    return None


def brier_error(confidence: float | None, hit: bool) -> float | None:
    """Per-observation calibration error ``(confidence - hit)²``.

    The proper-scoring-rule form that aggregates into the fusion calibration
    evidence (INV-16): a confident wrong call is penalized more than a timid
    one.
    """
    if confidence is None:
        return None
    target = 1.0 if hit else 0.0
    error = (confidence - target) ** 2
    return float(error)


def _favorable_extreme(path: tuple[PricePoint, ...], direction: SignalDirection) -> Decimal | None:
    if not path:
        return None
    if direction is SignalDirection.LONG:
        return max(point.high for point in path)
    return min(point.low for point in path)


def _adverse_extreme(path: tuple[PricePoint, ...], direction: SignalDirection) -> Decimal | None:
    if not path:
        return None
    if direction is SignalDirection.LONG:
        return min(point.low for point in path)
    return max(point.high for point in path)


def compute_trade_metrics(inputs: MetricsInput) -> TradeMetrics:
    """Derive the canonical :class:`TradeMetrics` block for one closed trade."""
    outcome = inputs.outcome
    entry = outcome.entry_price
    exit_price = outcome.exit_price
    direction = outcome.direction

    pnl_net = outcome.realized_pnl - outcome.costs
    slippage = outcome.slippage_total or Decimal("0")

    r_multiple: float | None = None
    if inputs.risk_amount is not None and inputs.risk_amount > 0:
        r_multiple = float(pnl_net / inputs.risk_amount)

    actual_return_pct = signed_return_pct(entry, exit_price, direction)
    alpha_pct: float | None = None
    if inputs.benchmark_return_pct is not None:
        alpha_pct = actual_return_pct - inputs.benchmark_return_pct
    elif inputs.expected_return_pct is not None:
        alpha_pct = actual_return_pct - inputs.expected_return_pct

    prediction_error_pct: float | None = None
    if inputs.expected_return_pct is not None:
        prediction_error_pct = abs(actual_return_pct - inputs.expected_return_pct)

    mae_pct: float | None = None
    mfe_pct: float | None = None
    entry_efficiency: float | None = None
    exit_efficiency: float | None = None
    best = _favorable_extreme(inputs.path, direction)
    worst = _adverse_extreme(inputs.path, direction)
    if best is not None and worst is not None:
        if direction is SignalDirection.LONG:
            mfe_pct = float((best - entry) / entry * 100)
            mae_pct = float((entry - worst) / entry * 100)
        else:
            mfe_pct = float((entry - best) / entry * 100)
            mae_pct = float((worst - entry) / entry * 100)
        mfe_pct = max(mfe_pct, 0.0)
        mae_pct = max(mae_pct, 0.0)
        if best != entry:
            entry_efficiency = float((exit_price - entry) / (best - entry))
        if best != worst:
            exit_efficiency = min(max(float((exit_price - worst) / (best - worst)), 0.0), 1.0)

    holding_seconds = int((outcome.closed_at - outcome.opened_at).total_seconds())
    regime = inputs.regime or outcome.regime_at_entry or "unknown"
    calibration = dict(inputs.signal_calibration_error or {})

    expected_r: float | None = None
    entry = outcome.entry_price
    if inputs.planned_stop is not None and inputs.planned_stop != entry:
        stop_distance = abs(inputs.planned_stop - entry)
        take_distance = (
            abs(inputs.planned_take - entry) if inputs.planned_take is not None else stop_distance
        )
        if stop_distance > 0:
            expected_r = float(take_distance / stop_distance)

    return TradeMetrics(
        pnl_gross=outcome.realized_pnl,
        pnl_net=pnl_net,
        fees=outcome.costs,
        slippage=slippage,
        r_multiple=r_multiple,
        alpha_pct=alpha_pct,
        mae_pct=mae_pct,
        mfe_pct=mfe_pct,
        holding_seconds=holding_seconds,
        entry_efficiency=entry_efficiency,
        exit_efficiency=exit_efficiency,
        signal_calibration_error=calibration,
        prediction_error_pct=prediction_error_pct,
        market_regime=regime,
        expected_return_pct=inputs.expected_return_pct,
        actual_return_pct=actual_return_pct,
        benchmark_return_pct=inputs.benchmark_return_pct,
        expected_r=expected_r,
    )
