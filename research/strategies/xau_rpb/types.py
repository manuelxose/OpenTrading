"""Domain types for the XAU_RPB strategy (spec §3-§8).

Pure value objects. No I/O, no broker calls, no clock reads — everything that
participates in a decision is passed in explicitly so the strategy is
deterministic and replayable (INV-3: nothing posterior to the decision bar is
reachable from here).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum, StrEnum

__all__ = [
    "Bar",
    "BrokerSpec",
    "Direction",
    "ExitReason",
    "PendingSignal",
    "Regime",
    "RejectReason",
    "SetupState",
    "Trade",
]


class Regime(StrEnum):
    """H1 market regime (spec §4.1). Only the two trend states permit entries."""

    INVALID = "REGIME_INVALID"
    TREND_UP = "REGIME_TREND_UP"
    TREND_DOWN = "REGIME_TREND_DOWN"
    RANGE = "REGIME_RANGE"
    HIGH_VOLATILITY = "REGIME_HIGH_VOLATILITY"

    @property
    def is_tradeable(self) -> bool:
        """True only for the two directional trend states (spec §4.2)."""
        return self in (Regime.TREND_UP, Regime.TREND_DOWN)


class SetupState(StrEnum):
    """M15 setup state machine (spec §5)."""

    SCANNING = "SCANNING"
    ARMED = "ARMED"
    PULLBACK_ACTIVE = "PULLBACK_ACTIVE"
    BREAKOUT_WINDOW = "BREAKOUT_WINDOW"
    SIGNAL_READY = "SIGNAL_READY"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    IN_POSITION = "IN_POSITION"


class Direction(int, Enum):
    """Trade direction. The integer value is the ``dir`` multiplier of spec §5."""

    LONG = 1
    SHORT = -1

    @property
    def code(self) -> str:
        return "LONG" if self is Direction.LONG else "SHORT"


class ExitReason(StrEnum):
    """Machine-readable exit reasons (spec §8.1). Recorded by the causing component."""

    STOP_LOSS = "STOP_LOSS"
    TARGET = "TARGET"
    ATR_TRAIL = "ATR_TRAIL"
    REGIME_INVALIDATION = "REGIME_INVALIDATION"
    TIME_EXIT = "TIME_EXIT"
    SESSION_EXIT = "SESSION_EXIT"
    RISK_KILL = "RISK_KILL"
    MANUAL = "MANUAL"
    BROKER_ERROR_RECOVERY = "BROKER_ERROR_RECOVERY"


class RejectReason(StrEnum):
    """Why an otherwise-formed signal did not become an order (spec §5.5, §9)."""

    SCORE_BELOW_THRESHOLD = "SCORE_BELOW_THRESHOLD"
    RISK_SIZE_ZERO = "RISK_SIZE_ZERO"
    SPREAD_TOO_WIDE = "SPREAD_TOO_WIDE"
    SESSION_BLOCKED = "SESSION_BLOCKED"
    NEWS_BLACKOUT = "NEWS_BLACKOUT"
    DAILY_LOSS_STOP = "DAILY_LOSS_STOP"
    WEEKLY_LOSS_STOP = "WEEKLY_LOSS_STOP"
    HARD_DRAWDOWN_KILL = "HARD_DRAWDOWN_KILL"
    POSITION_ALREADY_OPEN = "POSITION_ALREADY_OPEN"
    BROKER_SPEC_INVALID = "BROKER_SPEC_INVALID"
    STOP_LEVEL_VIOLATION = "STOP_LEVEL_VIOLATION"
    INSUFFICIENT_MARGIN = "INSUFFICIENT_MARGIN"
    INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"
    ATR_INVALID = "ATR_INVALID"
    DUPLICATE_SIGNAL = "DUPLICATE_SIGNAL"
    SAFE_MODE = "SAFE_MODE"


@dataclass(frozen=True, slots=True)
class Bar:
    """One closed OHLC bar. ``time`` is the bar's OPEN time, in broker server time."""

    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    spread_points: float = 0.0

    def is_valid(self) -> bool:
        """Structural sanity: positive prices and a consistent OHLC envelope."""
        if min(self.open, self.high, self.low, self.close) <= 0:
            return False
        if self.high < self.low:
            return False
        return self.low <= min(self.open, self.close) and self.high >= max(self.open, self.close)


@dataclass(frozen=True, slots=True)
class BrokerSpec:
    """Instrument specification as reported by the broker (spec §10).

    Never construct this from literals in production code — it exists so that
    *nothing* about the symbol is hardcoded. ``point`` and ``tick_size`` are the
    MT4 ``MODE_POINT`` / ``MODE_TICKSIZE`` values.
    """

    symbol: str
    point: float
    digits: int
    tick_value: float
    tick_size: float
    lot_size: float
    min_lot: float
    max_lot: float
    lot_step: float
    stop_level_points: float = 0.0
    freeze_level_points: float = 0.0
    swap_long: float = 0.0
    swap_short: float = 0.0

    def is_valid(self) -> bool:
        """Spec §7.1 validity gate: any failure means NO TRADE, never a default."""
        values = (self.point, self.tick_value, self.tick_size, self.min_lot, self.lot_step)
        if any(v <= 0 or v != v or v == float("inf") for v in values):
            return False
        return self.max_lot >= self.min_lot


@dataclass(frozen=True, slots=True)
class PendingSignal:
    """A fully-formed, score-passing entry signal awaiting execution guards."""

    signal_time: datetime
    direction: Direction
    entry_reference: float
    stop_price: float
    atr_at_signal: float
    breakout_reference: float
    pullback_depth_atr: float
    score: int
    regime: Regime


@dataclass(slots=True)
class Trade:
    """A position from entry to close, with the attribution needed for §42 metrics."""

    entry_time: datetime
    direction: Direction
    entry_price: float
    stop_price: float
    initial_stop_price: float
    lots: float
    atr_at_signal: float
    score: int
    regime_at_entry: Regime
    risk_amount: float
    exit_time: datetime | None = None
    exit_price: float | None = None
    exit_reason: ExitReason | None = None
    pnl: float = 0.0
    r_multiple: float = 0.0
    mae: float = 0.0
    mfe: float = 0.0
    bars_held: int = 0
    entry_slippage: float = 0.0
    exit_slippage: float = 0.0
    costs: float = 0.0

    @property
    def is_open(self) -> bool:
        return self.exit_time is None

    @property
    def risk_per_unit(self) -> float:
        """The initial R distance in price units (spec §8)."""
        return abs(self.entry_price - self.initial_stop_price)
