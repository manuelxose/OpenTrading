"""Account-level kill switches (spec §7.2).

Semantics that matter, and that the tests pin down:

* A breached daily or weekly stop blocks **new entries only**. Open positions keep
  being managed under §8 — stops are never widened or removed because a limit
  tripped.
* The hard drawdown kill blocks new entries until an operator resets it. It does
  **not** liquidate: forced liquidation converts a drawdown into a realized loss at
  the worst possible moment.
* Day and week boundaries are evaluated in **broker server time**, with the
  reference equity snapshotted at the first observation of the new period.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from .config import RiskPolicyParams
from .types import RejectReason

__all__ = ["RiskGovernor", "RiskState"]


def _week_key(moment: datetime) -> tuple[int, int]:
    iso = moment.isocalendar()
    return (iso.year, iso.week)


@dataclass(slots=True)
class RiskState:
    """Observable governor state (mirrored into telemetry, spec §28)."""

    day_start_equity: float = 0.0
    week_start_equity: float = 0.0
    peak_equity: float = 0.0
    current_day: date | None = None
    current_week: tuple[int, int] | None = None
    current_year: int | None = None
    hard_kill_active: bool = False
    soft_dd_active: bool = False
    daily_stop_hit: bool = False
    weekly_stop_hit: bool = False
    safe_mode: bool = False
    safe_mode_reason: str = ""


@dataclass(slots=True)
class RiskGovernor:
    """Evaluates the account-level limits. Independent of signal generation."""

    params: RiskPolicyParams
    state: RiskState = field(default_factory=RiskState)

    def observe(self, moment: datetime, equity: float) -> None:
        """Roll period boundaries and update peak equity. Call before every decision."""
        day = moment.date()
        week = _week_key(moment)

        if self.state.current_day != day:
            self.state.current_day = day
            self.state.day_start_equity = equity
            self.state.daily_stop_hit = False

        if self.state.current_week != week:
            self.state.current_week = week
            self.state.week_start_equity = equity
            self.state.weekly_stop_hit = False

        # RESEARCH-ONLY sample rescue (never enabled in production): a latched
        # hard kill would otherwise leave the rest of the dataset unmeasured.
        if (
            self.params.research_auto_reset_hard_kill
            and self.state.hard_kill_active
            and self.state.current_year != moment.year
        ):
            self.state.hard_kill_active = False
            self.state.peak_equity = equity
        self.state.current_year = moment.year

        if equity > self.state.peak_equity:
            self.state.peak_equity = equity

        self._evaluate(equity)

    def _evaluate(self, equity: float) -> None:
        s, p = self.state, self.params

        if s.day_start_equity > 0:
            daily_dd = (s.day_start_equity - equity) / s.day_start_equity * 100.0
            if daily_dd >= p.daily_loss_stop_pct:
                s.daily_stop_hit = True

        if s.week_start_equity > 0:
            weekly_dd = (s.week_start_equity - equity) / s.week_start_equity * 100.0
            if weekly_dd >= p.weekly_loss_stop_pct:
                s.weekly_stop_hit = True

        if s.peak_equity > 0:
            equity_dd = (s.peak_equity - equity) / s.peak_equity * 100.0
            s.soft_dd_active = equity_dd >= p.soft_dd_pct
            if equity_dd >= p.hard_dd_pct:
                # Latching: once tripped it stays tripped until an operator resets.
                s.hard_kill_active = True

    def entry_block_reason(self) -> RejectReason | None:
        """The reason new entries are blocked, or ``None`` when they are permitted.

        Ordered by severity so telemetry reports the most serious active block.
        """
        if self.state.safe_mode:
            return RejectReason.SAFE_MODE
        if self.state.hard_kill_active:
            return RejectReason.HARD_DRAWDOWN_KILL
        if self.state.weekly_stop_hit:
            return RejectReason.WEEKLY_LOSS_STOP
        if self.state.daily_stop_hit:
            return RejectReason.DAILY_LOSS_STOP
        return None

    def allows_new_entry(self) -> bool:
        return self.entry_block_reason() is None

    def effective_risk_pct(self) -> float:
        """Risk budget after the soft-drawdown de-risking step (spec §7.2)."""
        if self.state.soft_dd_active:
            return self.params.risk_pct * self.params.soft_dd_risk_multiplier
        return self.params.risk_pct

    def enter_safe_mode(self, reason: str) -> None:
        """Spec §13: inconsistent reconstruction -> manage only, open nothing."""
        self.state.safe_mode = True
        self.state.safe_mode_reason = reason

    def reset_hard_kill(self, operator: str) -> None:
        """Deliberate manual intervention — never automatic (spec §7.2)."""
        if not operator:
            raise ValueError("hard-kill reset requires an operator identity")
        self.state.hard_kill_active = False
