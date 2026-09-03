"""M15 pullback -> breakout setup state machine (spec §5).

The machine is the single authority for what a valid setup is. It holds no
market data of its own: every step is driven by an explicit closed-bar index, so
the same bar sequence always produces the same transitions, and no future bar is
reachable.

Transition rules are total and ordered exactly as the specification lists them —
first match wins. Every transition records a reason so the timeline can be
reconstructed from telemetry (spec §8 of the mandate: every transition is
deterministic, logged, testable, documented).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from .config import ResearchParams
from .indicators import is_finite
from .types import Bar, Direction, Regime, SetupState

__all__ = ["SetupMachine", "Transition"]


@dataclass(frozen=True, slots=True)
class Transition:
    """One state change, for the decision timeline."""

    bar_index: int
    from_state: SetupState
    to_state: SetupState
    reason: str


@dataclass(slots=True)
class SetupMachine:
    """The M15 setup state machine. One instance per strategy (one position, spec §7.2)."""

    params: ResearchParams
    state: SetupState = SetupState.SCANNING
    direction: Direction | None = None

    # Setup working fields (meaningless outside an active setup).
    pullback_bars: int = 0
    pullback_extreme: float = 0.0
    breakout_reference: float = 0.0
    swing_extreme: float = 0.0
    swing_origin: float = 0.0
    window_bars_left: int = 0
    setup_age_bars: int = 0
    depth_atr: float = 0.0

    transitions: list[Transition] = field(default_factory=list)

    # ------------------------------------------------------------------ helpers

    def _goto(self, index: int, target: SetupState, reason: str) -> None:
        if target is not self.state:
            self.transitions.append(Transition(index, self.state, target, reason))
        self.state = target

    def _reset(self, index: int, reason: str) -> None:
        """Return to SCANNING and clear every setup field (no stale state survives)."""
        self._goto(index, SetupState.SCANNING, reason)
        self.direction = None
        self.pullback_bars = 0
        self.pullback_extreme = 0.0
        self.breakout_reference = 0.0
        self.swing_extreme = 0.0
        self.swing_origin = 0.0
        self.window_bars_left = 0
        self.setup_age_bars = 0
        self.depth_atr = 0.0

    def _counter_trend(self, bar: Bar) -> bool:
        """A bar closing against ``direction`` (spec §5)."""
        assert self.direction is not None
        return self.direction.value * (bar.close - bar.open) < 0

    def _direction_for(self, regime: Regime) -> Direction | None:
        if regime is Regime.TREND_UP:
            return Direction.LONG
        if regime is Regime.TREND_DOWN:
            return Direction.SHORT
        return None

    def _update_swing(self, bars: Sequence[Bar], end_index: int) -> bool:
        """Measure the impulse leg over the lookback window ending at ``end_index``.

        ``end_index`` is the bar BEFORE the pullback began. Including the pullback
        bar itself would fold its own low into ``swing_origin``, which would make
        the structural-invalidation test unfalsifiable.
        """
        assert self.direction is not None
        lookback = self.params.impulse_lookback
        lo = end_index - lookback + 1
        if lo < 0 or end_index < 0:
            return False
        window = bars[lo : end_index + 1]
        highs = [b.high for b in window]
        lows = [b.low for b in window]
        if self.direction is Direction.LONG:
            self.swing_extreme = max(highs)
            self.swing_origin = min(lows)
        else:
            self.swing_extreme = min(lows)
            self.swing_origin = max(highs)
        return True

    def _compute_depth(self, atr_m15: float) -> float:
        if atr_m15 <= 0 or not is_finite(atr_m15):
            return float("nan")
        return abs(self.swing_extreme - self.pullback_extreme) / atr_m15

    def breakout_confirmed(self, bar: Bar, atr_m15: float) -> bool:
        """Spec §5.4 trigger: strict close-based break of the structure level."""
        assert self.direction is not None
        buffer_ = self.params.breakout_buffer_atr * atr_m15
        if self.direction is Direction.LONG:
            return bar.close > self.breakout_reference + buffer_
        return bar.close < self.breakout_reference - buffer_

    # -------------------------------------------------------------- main driver

    def on_closed_bar(
        self,
        bars: Sequence[Bar],
        index: int,
        regime: Regime,
        atr_m15: float,
    ) -> bool:
        """Advance the machine by one CLOSED M15 bar.

        Returns ``True`` when the machine has reached ``SIGNAL_READY`` on this bar,
        meaning a breakout was confirmed and the caller must now apply the score
        and the execution guards (spec §5.5).
        """
        if self.state in (SetupState.ORDER_SUBMITTED, SetupState.IN_POSITION):
            return False
        if index < 0 or index >= len(bars):
            return False

        bar = bars[index]

        # Fail closed on an unusable volatility reading (spec §15).
        if not is_finite(atr_m15) or atr_m15 <= 0:
            if self.state is not SetupState.SCANNING:
                self._reset(index, "ATR_INVALID")
            return False

        if self.state is not SetupState.SCANNING:
            self.setup_age_bars += 1

        if self.state is SetupState.SCANNING:
            return self._step_scanning(index, regime)
        if self.state is SetupState.ARMED:
            return self._step_armed(bars, index, regime, atr_m15)
        if self.state is SetupState.PULLBACK_ACTIVE:
            return self._step_pullback(bars, index, regime, atr_m15)
        if self.state is SetupState.BREAKOUT_WINDOW:
            return self._step_window(index, regime, atr_m15, bar)
        return False

    # ------------------------------------------------------------- state steps

    def _step_scanning(self, index: int, regime: Regime) -> bool:
        direction = self._direction_for(regime)
        if direction is None:
            return False
        self.direction = direction
        self.setup_age_bars = 0
        self._goto(index, SetupState.ARMED, f"REGIME_{regime.name}")
        return False

    def _regime_still_valid(self, index: int, regime: Regime) -> bool:
        """Common guard: the regime must still authorize the direction we armed on."""
        direction = self._direction_for(regime)
        if direction is None or direction is not self.direction:
            self._reset(index, "REGIME_INVALIDATED")
            return False
        return True

    def _step_armed(
        self, bars: Sequence[Bar], index: int, regime: Regime, atr_m15: float
    ) -> bool:
        if not self._regime_still_valid(index, regime):
            return False

        bar = bars[index]
        if not self._counter_trend(bar):
            return False

        # The impulse leg is what preceded this bar, so measure it up to index-1.
        if not self._update_swing(bars, index - 1):
            return False

        # A counter-trend close opens the pullback (spec §5.2 step 2).
        assert self.direction is not None
        p = self.params
        long_side = self.direction is Direction.LONG
        self.pullback_bars = 1
        prev = bars[index - 1]
        if long_side:
            self.pullback_extreme = bar.low
            self.breakout_reference = max(bar.high, prev.high)
        else:
            self.pullback_extreme = bar.high
            self.breakout_reference = min(bar.low, prev.low)
        self.depth_atr = self._compute_depth(atr_m15)

        # A "pullback" that immediately breaks the structure is not a pullback.
        if not is_finite(self.depth_atr) or self.depth_atr > p.max_pullback_depth_atr:
            self._reset(index, "PULLBACK_TOO_DEEP")
            return False
        structure_lost = (
            self.pullback_extreme < self.swing_origin
            if long_side
            else self.pullback_extreme > self.swing_origin
        )
        if structure_lost:
            self._reset(index, "STRUCTURE_LOST")
            return False

        self._goto(index, SetupState.PULLBACK_ACTIVE, "PULLBACK_STARTED")
        return False

    def _step_pullback(
        self, bars: Sequence[Bar], index: int, regime: Regime, atr_m15: float
    ) -> bool:
        if not self._regime_still_valid(index, regime):
            return False

        p = self.params
        bar = bars[index]
        assert self.direction is not None
        long_side = self.direction is Direction.LONG

        if self._counter_trend(bar):
            self.pullback_bars += 1
            if long_side:
                self.pullback_extreme = min(self.pullback_extreme, bar.low)
                self.breakout_reference = max(self.breakout_reference, bar.high)
            else:
                self.pullback_extreme = max(self.pullback_extreme, bar.high)
                self.breakout_reference = min(self.breakout_reference, bar.low)
            self.depth_atr = self._compute_depth(atr_m15)

            if self.pullback_bars > p.max_pullback_bars:
                self._reset(index, "PULLBACK_TOO_LONG")
                return False
            if not is_finite(self.depth_atr) or self.depth_atr > p.max_pullback_depth_atr:
                self._reset(index, "PULLBACK_TOO_DEEP")
                return False
            structure_lost = (
                self.pullback_extreme < self.swing_origin
                if long_side
                else self.pullback_extreme > self.swing_origin
            )
            if structure_lost:
                self._reset(index, "STRUCTURE_LOST")
                return False
            return False

        # First non-counter-trend bar: the pullback is over, validate it.
        if self.pullback_bars < p.min_pullback_bars:
            self._reset(index, "PULLBACK_TOO_SHORT")
            return False
        self.depth_atr = self._compute_depth(atr_m15)
        if not is_finite(self.depth_atr):
            self._reset(index, "ATR_INVALID")
            return False
        if self.depth_atr < p.min_pullback_depth_atr:
            self._reset(index, "PULLBACK_TOO_SHALLOW")
            return False
        if self.depth_atr > p.max_pullback_depth_atr:
            self._reset(index, "PULLBACK_TOO_DEEP")
            return False

        # The reference stays frozen at the PULLBACK structure. Folding this bar's
        # own high into it would make the recovery bar — the classic pullback
        # entry — structurally unable to trigger, and would bias every entry late.
        self.window_bars_left = p.breakout_window_bars
        self._goto(index, SetupState.BREAKOUT_WINDOW, "PULLBACK_COMPLETE")
        if self.breakout_confirmed(bar, atr_m15):
            self._goto(index, SetupState.SIGNAL_READY, "BREAKOUT_CONFIRMED")
            return True
        return False

    def _step_window(self, index: int, regime: Regime, atr_m15: float, bar: Bar) -> bool:
        if not self._regime_still_valid(index, regime):
            return False

        if self.breakout_confirmed(bar, atr_m15):
            self._goto(index, SetupState.SIGNAL_READY, "BREAKOUT_CONFIRMED")
            return True

        self.window_bars_left -= 1
        if self.window_bars_left <= 0:
            self._reset(index, "BREAKOUT_WINDOW_EXPIRED")
            return False
        if self.setup_age_bars >= self.params.max_setup_bars:
            self._reset(index, "SETUP_LIFETIME_EXCEEDED")
            return False
        return False

    # ------------------------------------------------- execution-side callbacks

    def on_order_submitted(self, index: int) -> None:
        self._goto(index, SetupState.ORDER_SUBMITTED, "ORDER_SUBMITTED")

    def on_filled(self, index: int) -> None:
        self._goto(index, SetupState.IN_POSITION, "FILLED")

    def on_rejected(self, index: int, reason: str) -> None:
        """Terminal broker rejection: the setup is abandoned, never retried blindly."""
        self._reset(index, f"REJECTED_{reason}")

    def on_signal_discarded(self, index: int, reason: str) -> None:
        """A SIGNAL_READY that failed the score or a guard (spec §5.5)."""
        self._reset(index, reason)

    def on_position_closed(self, index: int, reason: str) -> None:
        self._reset(index, f"CLOSED_{reason}")

    def adopt_recovered_position(self, direction: Direction) -> None:
        """Restart recovery (spec §13): resume IN_POSITION without re-entering."""
        self.state = SetupState.IN_POSITION
        self.direction = direction
