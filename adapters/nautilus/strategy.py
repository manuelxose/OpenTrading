"""Domain-side strategy contract and the minimal deterministic baseline.

The baseline is deliberately *outside* Nautilus: it only knows the canonical domain
types (``StrategyContext`` in, ``OrderIntent`` out). The identical ``DomainStrategy``
implementation can later run against PAPER or LIVE venues without changes (INV-2,
ADR-0007). No LLMs are involved anywhere in this module.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from statistics import mean
from typing import Protocol
from uuid import UUID, uuid5

from core.domain.enums import OperatingMode, OrderSide, OrderType, TimeInForce
from core.schemas import OrderIntent, PositionSnapshot
from core.schemas.base import Provenance

from adapters.nautilus.config import BaselineSmaConfig

__all__ = ["BaselineSmaStrategy", "DomainStrategy", "StrategyContext"]


class StrategyContext:
    """What a domain strategy may see at one bar (point-in-time, INV-3).

    Nothing posterior to ``as_of`` is ever exposed to a strategy.
    """

    def __init__(
        self,
        instrument_id: str,
        as_of: datetime,
        open_: Decimal,
        high: Decimal,
        low: Decimal,
        close: Decimal,
        volume: Decimal,
        position: PositionSnapshot | None,
        last_bid: Decimal | None,
        last_ask: Decimal | None,
        is_last_bar: bool,
        bars_remaining: int,
    ) -> None:
        self.instrument_id = instrument_id
        self.as_of = as_of
        self.open = open_
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
        self.position = position
        self.last_bid = last_bid
        self.last_ask = last_ask
        self.is_last_bar = is_last_bar
        self.bars_remaining = bars_remaining


class DomainStrategy(Protocol):
    """Any strategy that emits canonical ``OrderIntent``s from bar context.

    This protocol is the seam between the intelligence layer and the Nautilus
    execution venue — the same interface serves BACKTEST, PAPER and LIVE.
    """

    strategy_id: str
    strategy_version: str

    def on_bar(self, ctx: StrategyContext) -> list[OrderIntent]:
        """Return zero or more canonical order intents for the current bar."""
        ...


class BaselineSmaStrategy:
    """Minimal deterministic baseline: SMA crossover, long-only, market orders.

    - LONG when ``fast_sma > slow_sma`` and flat;
    - FLAT when ``fast_sma <= slow_sma`` and long (or on the last bar);
    - one MARKET ``OrderIntent`` per state change, fixed quantity.

    All emitted UUIDs are derived from a fixed namespace + a per-strategy counter,
    so two runs with the same config produce identical intents.
    """

    strategy_id = "baseline-sma"
    strategy_version = "1.0.0"

    def __init__(self, config: BaselineSmaConfig) -> None:
        self._config = config
        self._closes: list[Decimal] = []
        self._namespace = UUID(config.intent_namespace)
        self._sequence = 0
        self._is_long = False

    def on_bar(self, ctx: StrategyContext) -> list[OrderIntent]:
        self._closes.append(ctx.close)
        if len(self._closes) < self._config.slow_window:
            return []
        fast = mean(self._closes[-self._config.fast_window :])
        slow = mean(self._closes[-self._config.slow_window :])
        intents: list[OrderIntent] = []
        if fast > slow and not self._is_long:
            intents.append(self._intent(ctx, OrderSide.BUY))
            self._is_long = True
        should_exit = fast <= slow and self._is_long
        if self._config.exit_at_end and self._is_long and ctx.bars_remaining <= 2:
            # Exit one bar before the end so the closing order can still fill.
            should_exit = True
        if should_exit:
            intents.append(self._intent(ctx, OrderSide.SELL))
            self._is_long = False
        return intents

    def _intent(self, ctx: StrategyContext, side: OrderSide) -> OrderIntent:
        n = self._sequence
        self._sequence += 1
        order_intent_id = uuid5(self._namespace, f"{ctx.instrument_id}:{n}")
        produced_at = ctx.as_of
        return OrderIntent(
            order_intent_id=order_intent_id,
            risk_decision_id=uuid5(self._namespace, f"risk:{ctx.instrument_id}:{n}"),
            strategy_id=self.strategy_id,
            strategy_version=self.strategy_version,
            instrument_id=ctx.instrument_id,
            operating_mode=OperatingMode.BACKTEST,
            side=side,
            order_type=OrderType.MARKET,
            time_in_force=TimeInForce.GTC,
            quantity=self._config.quantity,
            max_slippage=Decimal("0"),
            sequence=n,
            created_by="baseline-sma",
            produced_at=produced_at,
            provenance=Provenance(producer="baseline-sma", produced_at=produced_at),
        )
