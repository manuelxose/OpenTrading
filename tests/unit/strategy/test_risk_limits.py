"""Account-level kill switches (spec §7.2).

The semantics under test are the ones that matter in an incident: which limits
block entries, which latch, which de-risk rather than stop, and the fact that a
tripped limit never liquidates on its own.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from research.strategies.xau_rpb import RejectReason, RiskGovernor, RiskPolicyParams

POLICY = RiskPolicyParams()
MONDAY = datetime(2024, 3, 4, 8, 0)


def governor() -> RiskGovernor:
    g = RiskGovernor(POLICY)
    g.observe(MONDAY, 100_000.0)
    return g


def test_a_fresh_governor_permits_entries() -> None:
    assert governor().allows_new_entry()


def test_daily_loss_stop_blocks_new_entries() -> None:
    g = governor()
    g.observe(MONDAY.replace(hour=14), 98_400.0)  # -1.6%, past the 1.5% stop

    assert not g.allows_new_entry()
    assert g.entry_block_reason() is RejectReason.DAILY_LOSS_STOP


def test_daily_stop_resets_on_the_next_day() -> None:
    g = governor()
    g.observe(MONDAY.replace(hour=14), 98_400.0)
    assert not g.allows_new_entry()

    g.observe(MONDAY.replace(day=5, hour=8), 98_400.0)
    assert g.allows_new_entry(), "a new day re-baselines the daily limit"


def test_weekly_loss_stop_blocks_and_outranks_the_daily_stop() -> None:
    g = governor()
    g.observe(MONDAY.replace(day=6), 96_500.0)  # -3.5% on the week

    assert g.entry_block_reason() is RejectReason.WEEKLY_LOSS_STOP


def test_weekly_stop_persists_across_days_within_the_same_week() -> None:
    g = governor()
    g.observe(MONDAY.replace(day=5), 96_500.0)
    g.observe(MONDAY.replace(day=7), 96_600.0)
    assert not g.allows_new_entry(), "a new day must not clear a weekly breach"


def test_soft_drawdown_halves_risk_without_blocking() -> None:
    g = governor()
    g.observe(MONDAY.replace(day=5), 94_500.0)  # -5.5% from peak

    assert g.state.soft_dd_active
    assert g.effective_risk_pct() == pytest.approx(POLICY.risk_pct * 0.5)
    assert g.entry_block_reason() is not RejectReason.HARD_DRAWDOWN_KILL


def test_hard_drawdown_kill_blocks_entries_and_latches() -> None:
    g = governor()
    g.observe(MONDAY.replace(day=5), 90_000.0)  # -10% from peak
    assert g.entry_block_reason() is RejectReason.HARD_DRAWDOWN_KILL

    # Recovering does NOT silently re-enable trading.
    g.observe(MONDAY.replace(day=8), 101_000.0)
    assert g.entry_block_reason() is RejectReason.HARD_DRAWDOWN_KILL


def test_hard_kill_requires_a_named_operator_to_reset() -> None:
    g = governor()
    g.observe(MONDAY.replace(day=5), 90_000.0)

    with pytest.raises(ValueError):
        g.reset_hard_kill("")

    g.reset_hard_kill("operator-on-call")
    # A LATER WEEK: the weekly stop tripped by the same drawdown must also expire
    # before entries resume, so the reset alone is deliberately not sufficient.
    g.observe(MONDAY.replace(day=12), 101_000.0)
    assert g.allows_new_entry()


def test_peak_equity_tracks_the_high_water_mark() -> None:
    g = governor()
    g.observe(MONDAY.replace(hour=10), 120_000.0)
    g.observe(MONDAY.replace(hour=11), 115_000.0)
    assert g.state.peak_equity == pytest.approx(120_000.0)


def test_drawdown_is_measured_from_the_peak_not_the_start() -> None:
    g = governor()
    g.observe(MONDAY.replace(hour=10), 200_000.0)          # new peak
    g.observe(MONDAY.replace(day=5, hour=9), 181_000.0)    # -9.5% from peak
    assert g.state.hard_kill_active


def test_safe_mode_outranks_every_other_block() -> None:
    g = governor()
    g.enter_safe_mode("duplicate strategy positions found on restart")

    assert g.entry_block_reason() is RejectReason.SAFE_MODE
    assert g.state.safe_mode_reason


def test_block_reasons_are_ordered_by_severity() -> None:
    g = governor()
    g.observe(MONDAY.replace(hour=14), 98_000.0)   # daily breach
    g.observe(MONDAY.replace(day=6), 89_000.0)     # weekly + hard breach
    assert g.entry_block_reason() is RejectReason.HARD_DRAWDOWN_KILL


def test_the_governor_never_liquidates_it_only_blocks_entries() -> None:
    """Spec §7.2: forced liquidation converts a drawdown into a realized loss."""
    g = governor()
    g.observe(MONDAY.replace(day=5), 85_000.0)

    assert not g.allows_new_entry()
    assert not hasattr(g, "close_all_positions"), (
        "the governor must not expose a liquidation path"
    )
