"""Pullback -> breakout state machine (spec §5).

Covers every valid transition, the invalid ones, both timeouts, the reset paths,
and the rule that carries the most weight in production: an intrabar spike that
does NOT close beyond the level must never confirm a breakout.
"""

from __future__ import annotations

from research.strategies.xau_rpb import Direction, Regime, ResearchParams, SetupState
from research.strategies.xau_rpb.state_machine import SetupMachine

from xau_rpb_builders import bar

ATR = 1.0


def params(**kw: object) -> ResearchParams:
    base = {"impulse_lookback": 2, "min_pullback_bars": 1, "max_pullback_bars": 3,
            "min_pullback_depth_atr": 0.2, "max_pullback_depth_atr": 5.0,
            "breakout_window_bars": 2, "breakout_buffer_atr": 0.1, "max_setup_bars": 12}
    base.update(kw)
    return ResearchParams(**base)  # type: ignore[arg-type]


def drive(machine: SetupMachine, bars: list, regime: Regime = Regime.TREND_UP) -> list[bool]:
    """Feed every bar to the machine and return the per-bar SIGNAL_READY flags."""
    return [machine.on_closed_bar(bars, i, regime, ATR) for i in range(len(bars))]


def _long_setup_bars() -> list:
    """Impulse up, one counter-trend bar, then a bar that closes above the structure."""
    return [
        bar(0, 100.0, 101.0, 99.8, 100.9),   # impulse
        bar(1, 100.9, 102.0, 100.8, 101.9),  # impulse, high 102.0
        bar(2, 101.9, 102.1, 100.5, 100.7),  # counter-trend pullback (close < open)
        bar(3, 100.7, 103.0, 100.6, 102.9),  # up bar closing beyond 102.1 + 0.1
    ]


def test_scanning_arms_only_in_a_trend_regime() -> None:
    machine = SetupMachine(params())
    bars = [bar(0, 100, 101, 99, 100.5)]

    machine.on_closed_bar(bars, 0, Regime.RANGE, ATR)
    assert machine.state is SetupState.SCANNING

    machine.on_closed_bar(bars, 0, Regime.TREND_UP, ATR)
    assert machine.state is SetupState.ARMED
    assert machine.direction is Direction.LONG


def test_trend_down_arms_the_short_side() -> None:
    machine = SetupMachine(params())
    bars = [bar(0, 100, 101, 99, 99.5)]
    machine.on_closed_bar(bars, 0, Regime.TREND_DOWN, ATR)
    assert machine.direction is Direction.SHORT


def test_full_long_sequence_reaches_signal_ready() -> None:
    machine = SetupMachine(params())
    flags = drive(machine, _long_setup_bars())

    assert flags[-1] is True, "the closing breakout bar must signal"
    assert machine.state is SetupState.SIGNAL_READY
    states = [t.to_state for t in machine.transitions]
    assert SetupState.ARMED in states
    assert SetupState.PULLBACK_ACTIVE in states
    assert SetupState.BREAKOUT_WINDOW in states


def test_full_short_sequence_is_symmetric() -> None:
    machine = SetupMachine(params())
    bars = [
        bar(0, 100.0, 100.2, 99.0, 99.1),
        bar(1, 99.1, 99.2, 98.0, 98.1),      # impulse down, low 98.0
        bar(2, 98.1, 99.5, 98.0, 99.3),      # counter-trend (close > open)
        bar(3, 99.3, 99.4, 97.0, 97.1),      # closes below 98.0 - 0.1
    ]
    flags = drive(machine, bars, Regime.TREND_DOWN)

    assert flags[-1] is True
    assert machine.direction is Direction.SHORT


def test_an_intrabar_spike_that_does_not_close_beyond_the_level_is_rejected() -> None:
    """The single most important guard: wicks never confirm a breakout (spec §5.4)."""
    machine = SetupMachine(params())
    bars = _long_setup_bars()
    # Same bar, but the close falls back inside the structure while the HIGH spikes far above.
    bars[3] = bar(3, 100.7, 105.0, 100.6, 101.0)
    flags = drive(machine, bars)

    assert not any(flags), "an intrabar spike must not produce a signal"
    assert machine.state is not SetupState.SIGNAL_READY


def test_breakout_must_clear_the_atr_buffer_not_merely_the_level() -> None:
    machine = SetupMachine(params(breakout_buffer_atr=0.5))
    bars = _long_setup_bars()
    # Closes above the reference (102.1) but inside the 0.5 * ATR buffer.
    bars[3] = bar(3, 100.7, 102.4, 100.6, 102.3)
    assert not any(drive(machine, bars))


def test_breakout_window_expires_and_resets_to_scanning() -> None:
    machine = SetupMachine(params(breakout_window_bars=2))
    bars = [*_long_setup_bars()[:3],
        bar(3, 100.7, 101.0, 100.6, 100.8),  # pullback ends, no breakout -> window opens
        bar(4, 100.8, 101.0, 100.6, 100.9),  # window bar 1, no breakout
        bar(5, 100.9, 101.0, 100.6, 100.95),  # window bar 2, no breakout -> expire
    ]
    drive(machine, bars)

    assert machine.state is SetupState.SCANNING
    assert any(t.reason == "BREAKOUT_WINDOW_EXPIRED" for t in machine.transitions)


def test_too_many_counter_trend_bars_abandons_the_setup() -> None:
    machine = SetupMachine(params(max_pullback_bars=2))
    bars = [
        bar(0, 100.0, 101.0, 99.8, 100.9),
        bar(1, 100.9, 102.0, 100.8, 101.9),
        bar(2, 101.9, 102.0, 101.0, 101.1),  # pullback 1
        bar(3, 101.1, 101.2, 100.5, 100.6),  # pullback 2
        bar(4, 100.6, 100.7, 100.0, 100.1),  # pullback 3 -> exceeds the cap
    ]
    drive(machine, bars)

    assert machine.state is SetupState.SCANNING
    assert any(t.reason == "PULLBACK_TOO_LONG" for t in machine.transitions)


def test_a_pullback_deeper_than_the_cap_is_rejected() -> None:
    machine = SetupMachine(params(max_pullback_depth_atr=0.5))
    bars = [
        bar(0, 100.0, 101.0, 99.8, 100.9),
        bar(1, 100.9, 105.0, 100.8, 104.9),  # swing extreme 105.0
        bar(2, 104.9, 105.0, 100.0, 100.1),  # retrace 5 ATR deep
    ]
    drive(machine, bars)

    assert machine.state is SetupState.SCANNING
    assert any(t.reason == "PULLBACK_TOO_DEEP" for t in machine.transitions)


def test_a_pullback_shallower_than_the_floor_is_rejected() -> None:
    machine = SetupMachine(params(min_pullback_depth_atr=1.0))
    bars = [
        bar(0, 100.0, 101.0, 99.8, 100.9),
        bar(1, 100.9, 102.0, 100.8, 101.9),
        bar(2, 101.9, 101.95, 101.8, 101.85),  # a token 0.2 retrace
        bar(3, 101.85, 102.5, 101.8, 102.4),   # pullback ends
    ]
    drive(machine, bars)
    assert any(t.reason == "PULLBACK_TOO_SHALLOW" for t in machine.transitions)


def test_losing_the_impulse_origin_resets_the_setup() -> None:
    machine = SetupMachine(params(max_pullback_depth_atr=50.0))
    bars = [
        bar(0, 100.0, 101.0, 99.0, 100.9),   # origin low 99.0
        bar(1, 100.9, 102.0, 100.8, 101.9),
        bar(2, 101.9, 102.0, 98.0, 98.1),    # trades below the origin
    ]
    drive(machine, bars)

    assert machine.state is SetupState.SCANNING
    assert any(t.reason == "STRUCTURE_LOST" for t in machine.transitions)


def test_regime_flipping_mid_setup_abandons_it() -> None:
    machine = SetupMachine(params())
    bars = _long_setup_bars()
    machine.on_closed_bar(bars, 0, Regime.TREND_UP, ATR)
    machine.on_closed_bar(bars, 1, Regime.TREND_UP, ATR)
    machine.on_closed_bar(bars, 2, Regime.TREND_UP, ATR)
    assert machine.state is SetupState.PULLBACK_ACTIVE

    machine.on_closed_bar(bars, 3, Regime.RANGE, ATR)
    assert machine.state is SetupState.SCANNING
    assert any(t.reason == "REGIME_INVALIDATED" for t in machine.transitions)


def test_an_invalid_atr_fails_closed_and_clears_the_setup() -> None:
    machine = SetupMachine(params())
    bars = _long_setup_bars()
    machine.on_closed_bar(bars, 0, Regime.TREND_UP, ATR)
    assert machine.state is SetupState.ARMED

    machine.on_closed_bar(bars, 1, Regime.TREND_UP, float("nan"))
    assert machine.state is SetupState.SCANNING


def test_zero_atr_never_produces_a_signal() -> None:
    machine = SetupMachine(params())
    assert not any(
        machine.on_closed_bar(_long_setup_bars(), i, Regime.TREND_UP, 0.0) for i in range(4)
    )


def test_the_machine_is_inert_while_a_position_is_open() -> None:
    machine = SetupMachine(params())
    machine.adopt_recovered_position(Direction.LONG)
    assert not any(drive(machine, _long_setup_bars()))
    assert machine.state is SetupState.IN_POSITION


def test_reset_clears_every_setup_field() -> None:
    machine = SetupMachine(params())
    drive(machine, _long_setup_bars())
    assert machine.state is SetupState.SIGNAL_READY

    machine.on_signal_discarded(3, "SCORE_BELOW_THRESHOLD")
    assert machine.state is SetupState.SCANNING
    assert machine.direction is None
    assert machine.pullback_bars == 0
    assert machine.breakout_reference == 0.0
    assert machine.window_bars_left == 0


def test_position_lifecycle_callbacks_walk_the_declared_states() -> None:
    machine = SetupMachine(params())
    drive(machine, _long_setup_bars())

    machine.on_order_submitted(3)
    assert machine.state is SetupState.ORDER_SUBMITTED
    machine.on_filled(3)
    assert machine.state is SetupState.IN_POSITION
    machine.on_position_closed(4, "STOP_LOSS")
    assert machine.state is SetupState.SCANNING


def test_a_terminal_rejection_returns_to_scanning_without_retrying() -> None:
    machine = SetupMachine(params())
    drive(machine, _long_setup_bars())
    machine.on_order_submitted(3)
    machine.on_rejected(3, "INVALID_VOLUME")

    assert machine.state is SetupState.SCANNING
    assert machine.direction is None


def test_every_transition_is_recorded_with_a_reason() -> None:
    machine = SetupMachine(params())
    drive(machine, _long_setup_bars())
    assert machine.transitions, "transitions must be observable for the decision timeline"
    assert all(t.reason for t in machine.transitions)
