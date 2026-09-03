"""High-impact news risk filter (spec §12).

Two properties are non-negotiable:

* **News never predicts direction.** It only blocks new entries inside a blackout
  window. Direction comes from the regime and the breakout, nothing else.
* **The calendar is a frozen, versioned CSV — never a live API.** `WebRequest()`
  does not run inside the MT4 Strategy Tester, and a backtest whose inputs can
  change between runs is not reproducible.

A missing or malformed file **fails closed** when ``required=True``: it blocks all
new entries rather than silently trading through an unknown calendar (spec §15).
"""

from __future__ import annotations

import csv
from bisect import bisect_left
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

__all__ = ["NewsCalendar", "NewsEvent", "NewsFileError"]

HIGH_IMPACT = {"HIGH", "H", "3"}


class NewsFileError(ValueError):
    """The calendar file is missing, unreadable or malformed."""


@dataclass(frozen=True, slots=True)
class NewsEvent:
    event_time_utc: datetime
    currency: str
    impact: str
    name: str


class NewsCalendar:
    """Frozen high-impact calendar with an O(log n) blackout query."""

    def __init__(
        self,
        events: list[NewsEvent],
        *,
        block_before_min: int = 30,
        block_after_min: int = 15,
        required: bool = False,
        loaded: bool = True,
        source: str = "",
    ) -> None:
        self._events = sorted(events, key=lambda e: e.event_time_utc)
        self._times = [e.event_time_utc for e in self._events]
        self._before = timedelta(minutes=block_before_min)
        self._after = timedelta(minutes=block_after_min)
        self._required = required
        self._loaded = loaded
        self.source = source

    def __len__(self) -> int:
        return len(self._events)

    @property
    def is_usable(self) -> bool:
        return self._loaded or not self._required

    @classmethod
    def empty(cls, *, required: bool = False) -> NewsCalendar:
        """No calendar configured. Blocks everything when the filter is required."""
        return cls([], required=required, loaded=not required, source="<none>")

    @classmethod
    def failed(cls, source: str) -> NewsCalendar:
        """A calendar that could not be loaded: fails closed on every query."""
        return cls([], required=True, loaded=False, source=source)

    @classmethod
    def from_csv(
        cls,
        path: str | Path,
        *,
        block_before_min: int = 30,
        block_after_min: int = 15,
        required: bool = False,
        currencies: tuple[str, ...] = ("USD",),
        strict: bool = False,
    ) -> NewsCalendar:
        """Load the frozen CSV (schema in spec §12).

        With ``strict=False`` a malformed *row* is skipped; a malformed *file*
        (missing, unreadable, wrong header) still fails closed.
        """
        p = Path(path)
        if not p.is_file():
            if strict:
                raise NewsFileError(f"news calendar not found: {p}")
            return cls.failed(str(p)) if required else cls.empty(required=False)

        events: list[NewsEvent] = []
        try:
            with p.open("r", encoding="utf-8-sig", newline="") as fh:
                reader = csv.DictReader(fh)
                if reader.fieldnames is None or "event_time_utc" not in reader.fieldnames:
                    raise NewsFileError(f"news calendar missing 'event_time_utc' header: {p}")
                for row in reader:
                    event = _parse_row(row, currencies)
                    if event is not None:
                        events.append(event)
        except NewsFileError:
            if strict:
                raise
            return cls.failed(str(p))
        except (OSError, UnicodeDecodeError) as exc:
            if strict:
                raise NewsFileError(f"unreadable news calendar {p}: {exc}") from exc
            return cls.failed(str(p))

        return cls(
            events,
            block_before_min=block_before_min,
            block_after_min=block_after_min,
            required=required,
            loaded=True,
            source=str(p),
        )

    def is_blackout(self, moment_utc: datetime) -> bool:
        """True when new entries must be blocked at ``moment_utc``."""
        if not self.is_usable:
            return True  # fail closed
        if not self._events:
            return False
        if moment_utc.tzinfo is None:
            moment_utc = moment_utc.replace(tzinfo=UTC)

        # The first event that could still be blocking is at moment - after.
        idx = bisect_left(self._times, moment_utc - self._after)
        while idx < len(self._times):
            event_time = self._times[idx]
            if event_time - self._before > moment_utc:
                return False
            if event_time - self._before <= moment_utc <= event_time + self._after:
                return True
            idx += 1
        return False


def _parse_row(row: dict[str, str], currencies: tuple[str, ...]) -> NewsEvent | None:
    raw_time = (row.get("event_time_utc") or "").strip()
    if not raw_time:
        return None
    try:
        moment = datetime.fromisoformat(raw_time.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)

    impact = (row.get("impact") or "").strip().upper()
    if impact not in HIGH_IMPACT:
        return None
    currency = (row.get("currency") or "").strip().upper()
    if currencies and currency not in currencies:
        return None

    return NewsEvent(
        event_time_utc=moment.astimezone(UTC),
        currency=currency,
        impact=impact,
        name=(row.get("event_name") or "").strip(),
    )
