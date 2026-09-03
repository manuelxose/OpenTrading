"""Broker-aware position sizing (spec §7.1).

Two rules carry the whole safety argument here and are enforced without exception:

1. **Always round DOWN** to the broker lot step. Rounding up silently exceeds the
   risk mandate.
2. **Never round up to the minimum lot.** If the broker's minimum lot implies more
   risk than ``risk_pct`` allows, the answer is *no trade* — not a bigger trade.

Nothing about the instrument is assumed: every quantity comes from the
:class:`BrokerSpec` the venue reported (spec §10).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .indicators import is_finite
from .types import BrokerSpec, RejectReason

__all__ = ["SizingResult", "calculate_lots", "floor_to_step"]


@dataclass(frozen=True, slots=True)
class SizingResult:
    """Outcome of a sizing attempt. ``lots == 0`` always carries a ``reject_reason``."""

    lots: float
    risk_money: float
    risk_per_lot: float
    stop_distance: float
    actual_risk: float
    reject_reason: RejectReason | None = None

    @property
    def is_tradeable(self) -> bool:
        return self.lots > 0 and self.reject_reason is None


def floor_to_step(value: float, step: float) -> float:
    """Round ``value`` DOWN to a multiple of ``step``, guarding float representation.

    ``math.floor`` on a ratio such as ``0.3/0.1 = 2.9999...`` would silently drop a
    whole step, so the ratio is nudged by a relative epsilon before flooring.
    """
    if step <= 0:
        raise ValueError("lot step must be > 0")
    if value <= 0:
        return 0.0
    ratio = value / step
    # Relative epsilon: a true 1.0 can arrive as 0.999999999 after division, and
    # flooring that would silently discard a whole lot step. The nudge is float
    # noise compensation, never a rounding-up rule.
    nudged = math.floor(ratio + 1e-9 * max(1.0, abs(ratio)))
    return round(nudged * step, 8)


def calculate_lots(
    *,
    equity: float,
    risk_pct: float,
    entry_price: float,
    stop_price: float,
    spec: BrokerSpec,
) -> SizingResult:
    """Derive lot size from equity, risk budget and the ACTUAL stop distance.

    The lot size is an output of the stop, never an input — which is what makes a
    fixed-lot production default (and every martingale variant) unrepresentable
    here (spec §7.2).
    """
    if not spec.is_valid():
        return SizingResult(0.0, 0.0, 0.0, 0.0, 0.0, RejectReason.BROKER_SPEC_INVALID)
    if not all(is_finite(v) for v in (equity, risk_pct, entry_price, stop_price)):
        return SizingResult(0.0, 0.0, 0.0, 0.0, 0.0, RejectReason.BROKER_SPEC_INVALID)
    if equity <= 0 or risk_pct <= 0:
        return SizingResult(0.0, 0.0, 0.0, 0.0, 0.0, RejectReason.RISK_SIZE_ZERO)

    stop_distance = abs(entry_price - stop_price)
    if stop_distance <= 0:
        return SizingResult(0.0, 0.0, 0.0, 0.0, 0.0, RejectReason.RISK_SIZE_ZERO)

    # MT4 MODE_TICKSIZE is the minimal PRICE increment (0.01 on a 2-digit XAUUSD),
    # NOT a count of points. Multiplying it by Point — as the source audit's sample
    # code does — understates every position by a factor of 1/Point (100x here).
    tick_size_price = spec.tick_size
    if tick_size_price <= 0:
        return SizingResult(0.0, 0.0, 0.0, stop_distance, 0.0, RejectReason.BROKER_SPEC_INVALID)

    risk_money = equity * risk_pct / 100.0
    ticks = stop_distance / tick_size_price
    risk_per_lot = ticks * spec.tick_value
    if risk_per_lot <= 0 or not is_finite(risk_per_lot):
        return SizingResult(0.0, risk_money, 0.0, stop_distance, 0.0,
                            RejectReason.BROKER_SPEC_INVALID)

    lots = floor_to_step(risk_money / risk_per_lot, spec.lot_step)

    # Cap at the venue maximum, still on a valid step boundary.
    if lots > spec.max_lot:
        lots = floor_to_step(spec.max_lot, spec.lot_step)

    # The mandate rule: below the minimum we do NOT trade. We never round up.
    if lots < spec.min_lot:
        return SizingResult(0.0, risk_money, risk_per_lot, stop_distance, 0.0,
                            RejectReason.RISK_SIZE_ZERO)

    actual_risk = lots * risk_per_lot
    if actual_risk > risk_money * (1.0 + 1e-9):
        # Defensive: flooring can never increase risk, so this is a broken spec.
        return SizingResult(0.0, risk_money, risk_per_lot, stop_distance, 0.0,
                            RejectReason.RISK_SIZE_ZERO)

    return SizingResult(lots, risk_money, risk_per_lot, stop_distance, actual_risk)
