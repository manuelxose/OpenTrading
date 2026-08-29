"""Deterministic simulated-venue order rejection (ADR-0007: rejection simulation).

Structural rules (lot limits, price guard, market hours) are always evaluated
against the domain ``Instrument`` and the current market. The optional random rule
draws from a seed-derived RNG, so rejection patterns are reproducible.
"""

from __future__ import annotations

import random
from datetime import datetime
from decimal import Decimal

from core.domain.enums import OrderSide, OrderType
from core.schemas import Instrument, OrderIntent

from adapters.nautilus.config import RejectionConfig

__all__ = ["OrderRejectionSim"]

#: Rejection reason codes (free text on ExecutionReport.reject_reason).
SIZE_BELOW_MINIMUM = "SIZE_BELOW_MINIMUM"
SIZE_ABOVE_MAXIMUM = "SIZE_ABOVE_MAXIMUM"
LOT_STEP_INVALID = "LOT_STEP_INVALID"
PRICE_OUTSIDE_MARKET = "PRICE_OUTSIDE_MARKET"
MARKET_CLOSED = "MARKET_CLOSED"
SIMULATED_REJECTION = "SIMULATED_REJECTION"


class OrderRejectionSim:
    """Deterministic rejection rule chain evaluated per ``OrderIntent``."""

    def __init__(self, config: RejectionConfig, seed: int, instrument: Instrument) -> None:
        self._config = config
        self._instrument = instrument
        self._rng = random.Random(seed + config.seed_offset + 530_843)
        self._market_start: datetime | None = None
        self._market_end: datetime | None = None

    def set_session(self, start: datetime, end: datetime) -> None:
        self._market_start = start
        self._market_end = end

    def reason(
        self,
        intent: OrderIntent,
        now: datetime,
        last_bid: Decimal | None,
        last_ask: Decimal | None,
    ) -> str | None:
        """Return a rejection reason, or ``None`` when the order may proceed."""
        if self._config.enforce_market_hours and not self._in_session(now):
            return MARKET_CLOSED
        if self._config.enforce_lot_rules:
            reason = self._lot_rule_reason(intent)
            if reason is not None:
                return reason
        if self._config.enforce_price_guard:
            reason = self._price_guard_reason(intent, last_bid, last_ask)
            if reason is not None:
                return reason
        if self._config.probability > 0 and self._rng.random() < self._config.probability:
            return SIMULATED_REJECTION
        return None

    def _in_session(self, now: datetime) -> bool:
        if self._market_start is not None and now < self._market_start:
            return False
        return not (self._market_end is not None and now > self._market_end)

    def _lot_rule_reason(self, intent: OrderIntent) -> str | None:
        instrument = self._instrument
        quantity = intent.quantity
        min_units = instrument.min_lot * instrument.lot_size
        max_units = instrument.max_lot * instrument.lot_size
        step_units = instrument.lot_step * instrument.lot_size
        if quantity < min_units:
            return SIZE_BELOW_MINIMUM
        if quantity > max_units:
            return SIZE_ABOVE_MAXIMUM
        if ((quantity - min_units) / step_units) % 1 != 0:
            return LOT_STEP_INVALID
        return None

    def _price_guard_reason(
        self, intent: OrderIntent, last_bid: Decimal | None, last_ask: Decimal | None
    ) -> str | None:
        if intent.order_type is OrderType.MARKET or intent.price is None:
            return None
        if intent.order_type is OrderType.LIMIT:
            if intent.side is OrderSide.BUY and last_ask is not None and intent.price > last_ask:
                return PRICE_OUTSIDE_MARKET
            if intent.side is OrderSide.SELL and last_bid is not None and intent.price < last_bid:
                return PRICE_OUTSIDE_MARKET
        if intent.order_type in (OrderType.STOP, OrderType.STOP_LIMIT):
            if intent.side is OrderSide.BUY and last_ask is not None and intent.price < last_ask:
                return PRICE_OUTSIDE_MARKET
            if intent.side is OrderSide.SELL and last_bid is not None and intent.price > last_bid:
                return PRICE_OUTSIDE_MARKET
        return None
