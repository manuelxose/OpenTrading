"""Clock abstraction (architecture §5, INV-3).

No production component may call ``datetime.now()`` directly for domain decisions —
everything takes a :class:`Clock`:

- :class:`SystemClock` — wall clock (live modes, operational code).
- :class:`VirtualClock` — explicit, deterministic simulation time (BACKTEST, replay).

Both always yield timezone-aware UTC datetimes.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

from core.schemas.base import ensure_utc

__all__ = ["Clock", "SystemClock", "VirtualClock"]


class Clock(Protocol):
    def now(self) -> datetime:
        """Current time as timezone-aware UTC."""
        ...


class SystemClock:
    """The only place allowed to read the real wall clock."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class VirtualClock:
    """Deterministic simulation clock.

    Time only advances through explicit :meth:`advance` / :meth:`set` calls; repeated
    :meth:`now` calls return the identical instant, so two clocks driven by the same
    sequence of calls observe exactly the same timeline.
    """

    def __init__(self, start: datetime) -> None:
        self._now = ensure_utc(start)

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta = timedelta(seconds=1)) -> datetime:
        """Move forward by ``delta`` (strictly positive) and return the new time."""
        if delta <= timedelta(0):
            raise ValueError("VirtualClock.advance requires a positive delta")
        self._now += delta
        return self._now

    def set(self, moment: datetime) -> datetime:
        """Jump to ``moment``; moving backwards is refused (monotonic simulation time)."""
        moment_utc = ensure_utc(moment)
        if moment_utc < self._now:
            raise ValueError(
                f"VirtualClock cannot move backwards: now={self._now.isoformat()}, "
                f"requested={moment_utc.isoformat()}"
            )
        self._now = moment_utc
        return self._now
