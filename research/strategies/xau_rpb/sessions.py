"""Session and time normalization (spec §11).

The failure this module exists to prevent: hardcoding a broker server hour (the
audited `GOLD_ORB` uses `01:02` server time) and then discovering that the
backtest and the live terminal disagree, or that the rule silently shifts twice a
year at DST transitions.

The chain is explicit and reproducible:

    broker server timestamp -> broker UTC offset -> UTC -> London / New York local

The broker offset is an input, never a guess. When it is unknown the caller must
supply it or the system fails closed (spec §15) rather than assuming UTC+2.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

__all__ = ["SessionFlags", "SessionResolver", "us_dst_broker_offset"]

LONDON = ZoneInfo("Europe/London")
NEW_YORK = ZoneInfo("America/New_York")
TOKYO = ZoneInfo("Asia/Tokyo")

# Local-exchange windows (spec §11).
LONDON_OPEN, LONDON_CLOSE = (8, 0), (16, 30)
NEW_YORK_OPEN, NEW_YORK_CLOSE = (8, 0), (17, 0)
ASIA_OPEN, ASIA_CLOSE = (9, 0), (17, 0)
# Rollover is defined in UTC because it follows the broker day, not an exchange.
ROLLOVER_START_UTC, ROLLOVER_END_UTC = 21, 23


@dataclass(frozen=True, slots=True)
class SessionFlags:
    """Which liquidity windows a given instant falls into."""

    utc: datetime
    london: bool
    new_york: bool
    overlap: bool
    asian: bool
    rollover: bool

    @property
    def label(self) -> str:
        """Single canonical name for per-session attribution reporting (spec §40)."""
        if self.rollover:
            return "ROLLOVER"
        if self.overlap:
            return "OVERLAP"
        if self.london:
            return "LONDON"
        if self.new_york:
            return "NEW_YORK"
        if self.asian:
            return "ASIAN"
        return "OFF_SESSION"


def _within(moment_local: datetime, start: tuple[int, int], end: tuple[int, int]) -> bool:
    minutes = moment_local.hour * 60 + moment_local.minute
    return start[0] * 60 + start[1] <= minutes < end[0] * 60 + end[1]


def us_dst_broker_offset(broker_time: datetime) -> float:
    """Offset for the common MetaQuotes-style server that follows **US** DST.

    Measured on IC Markets XAUUSD M15 history: the daily maintenance break sits at
    server hour 00:00 all year round, while gold's break in UTC moves between
    22:00-23:00 (winter) and 21:00-22:00 (summer). A server whose break stays put
    in its own clock while the UTC break moves must itself be moving — i.e. it is
    UTC+2 in winter and UTC+3 in summer.

    A FIXED offset would therefore misplace every session boundary by one hour for
    roughly half of each year.

    The switch is evaluated against the broker timestamp directly; near the two
    transition hours the result can be off by one hour for a single bar, which is
    immaterial to a session filter and avoids a circular UTC/offset dependency.
    """
    year, month, day = broker_time.year, broker_time.month, broker_time.day
    if month < 3 or month > 11:
        return 2.0
    if 3 < month < 11:
        return 3.0
    if month == 3:
        first_sunday = 1
        while day_of_week(year, 3, first_sunday) != 0:
            first_sunday += 1
        return 3.0 if day >= first_sunday + 7 else 2.0
    first_sunday_nov = 1
    while day_of_week(year, 11, first_sunday_nov) != 0:
        first_sunday_nov += 1
    return 3.0 if day < first_sunday_nov else 2.0


def day_of_week(year: int, month: int, day: int) -> int:
    """Day of week, 0 = Sunday (Sakamoto).

    Mirrors ``DayOfWeekFor`` in ``mt4/Include/xau_rpb/Sessions.mqh`` so both sides
    compute DST transitions identically.
    """
    table = (0, 3, 2, 5, 0, 3, 5, 1, 4, 6, 2, 4)
    y = year - 1 if month < 3 else year
    return (y + y // 4 - y // 100 + y // 400 + table[month - 1] + day) % 7


class SessionResolver:
    """Converts broker server time to UTC and derives DST-aware session flags.

    ``broker_utc_offset_hours`` accepts either a constant or a callable resolving
    the offset per timestamp. Most MetaQuotes-style brokers (IC Markets among
    them) shift with US DST, so a constant is wrong for half the year — pass
    :func:`us_dst_broker_offset` for those.
    """

    def __init__(
        self,
        broker_utc_offset_hours: float | Callable[[datetime], float],
        *,
        allow_asian: bool = False,
        block_rollover: bool = True,
    ) -> None:
        self._offset_fn: Callable[[datetime], float]
        if callable(broker_utc_offset_hours):
            self._offset_fn = broker_utc_offset_hours
            self._constant: float | None = None
        else:
            constant = float(broker_utc_offset_hours)
            self._offset_fn = lambda _moment: constant
            self._constant = constant
        self._allow_asian = allow_asian
        self._block_rollover = block_rollover

    @property
    def broker_utc_offset_hours(self) -> float | None:
        """The constant offset, or ``None`` when it is resolved per timestamp."""
        return self._constant

    def offset_at(self, broker_time: datetime) -> float:
        """The offset actually applied at ``broker_time`` (recorded in telemetry)."""
        return self._offset_fn(broker_time)

    def to_utc(self, broker_time: datetime) -> datetime:
        """Broker server timestamp -> UTC. Naive input is treated as server-local."""
        if broker_time.tzinfo is not None:
            return broker_time.astimezone(UTC)
        offset = timedelta(hours=self._offset_fn(broker_time))
        return (broker_time - offset).replace(tzinfo=UTC)

    def flags(self, broker_time: datetime) -> SessionFlags:
        """Full session classification for a broker-time instant."""
        utc = self.to_utc(broker_time)
        london_local = utc.astimezone(LONDON)
        ny_local = utc.astimezone(NEW_YORK)
        tokyo_local = utc.astimezone(TOKYO)

        in_london = _within(london_local, LONDON_OPEN, LONDON_CLOSE)
        in_ny = _within(ny_local, NEW_YORK_OPEN, NEW_YORK_CLOSE)
        in_asia = _within(tokyo_local, ASIA_OPEN, ASIA_CLOSE)
        in_rollover = ROLLOVER_START_UTC <= utc.hour < ROLLOVER_END_UTC

        return SessionFlags(
            utc=utc,
            london=in_london,
            new_york=in_ny,
            overlap=in_london and in_ny,
            asian=in_asia,
            rollover=in_rollover,
        )

    def is_permitted(self, broker_time: datetime) -> bool:
        """V1 default permitted window: London or New York, excluding rollover."""
        f = self.flags(broker_time)
        if self._block_rollover and f.rollover:
            return False
        if f.london or f.new_york:
            return True
        return bool(self._allow_asian and f.asian)


def infer_broker_utc_offset(broker_time: datetime, known_utc: datetime) -> float:
    """Derive the server offset from one paired observation, rounded to 15 minutes.

    Used only at startup, and the result is logged. Guessing a default here would
    be exactly the mistake spec §11 forbids.
    """
    delta = (broker_time.replace(tzinfo=UTC) - known_utc).total_seconds() / 3600.0
    return round(delta * 4.0) / 4.0
