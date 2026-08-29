"""Silver-layer data quality: flags, duplicate handling, missing-bar detection.

Everything here is deterministic: given the same bronze rows and the same clock
instant, the engine always produces the same silver rows, the same flags and the
same gap list (Phase 1 DoD reproducibility).
"""

from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timedelta
from itertools import pairwise

from core.clock.clocks import Clock
from core.domain.enums import DataQualityFlag, Timeframe
from core.schemas.market_data import Bar, BarGap

from adapters.market_data.hashing import canonical_bar_bytes

__all__ = ["TIMEFRAME_STEP", "DataQualityEngine", "QualityOutcome"]

#: Deterministic bar-grid steps. D1/W1/MN1 use calendar arithmetic to stay
#: aligned with real session grids; intraday frames are fixed UTC durations.
#: DST-shifted session grids are a documented out-of-scope case for now.
TIMEFRAME_STEP: dict[Timeframe, timedelta] = {
    Timeframe.M1: timedelta(minutes=1),
    Timeframe.M5: timedelta(minutes=5),
    Timeframe.M15: timedelta(minutes=15),
    Timeframe.M30: timedelta(minutes=30),
    Timeframe.H1: timedelta(hours=1),
    Timeframe.H4: timedelta(hours=4),
}

#: Clock tolerance (sanity margin) before a timestamp counts as future-dated.
_FUTURE_TOLERANCE = timedelta(minutes=1)


class QualityOutcome:
    """Result of one silver pass: flagged bars, dropped duplicates, gaps."""

    def __init__(
        self,
        silver_bars: tuple[Bar, ...],
        gaps: tuple[BarGap, ...],
        duplicate_count: int,
        stale_count: int,
        anomaly_count: int,
        future_dated_count: int,
    ) -> None:
        self.silver_bars = silver_bars
        self.gaps = gaps
        self.duplicate_count = duplicate_count
        self.stale_count = stale_count
        self.anomaly_count = anomaly_count
        self.future_dated_count = future_dated_count


class DataQualityEngine:
    """Flagging + dedup + missing-bar detection (silver layer)."""

    def __init__(self, stale_after: timedelta = timedelta(hours=1)) -> None:
        self._stale_after = stale_after

    def process(self, bronze_bars: tuple[Bar, ...], clock: Clock) -> QualityOutcome:
        now = clock.now()
        flagged = tuple(self._flag(bar, now) for bar in bronze_bars)
        silver, duplicate_count = self._deduplicate(flagged)
        gaps = self._detect_missing_bars(silver, now)
        stale_count = sum(1 for bar in silver if DataQualityFlag.STALE in bar.quality_flags)
        anomaly_count = sum(
            1 for bar in silver if DataQualityFlag.PRICE_ANOMALY in bar.quality_flags
        )
        future_count = sum(1 for bar in silver if DataQualityFlag.FUTURE_DATED in bar.quality_flags)
        return QualityOutcome(
            silver_bars=silver,
            gaps=gaps,
            duplicate_count=duplicate_count,
            stale_count=stale_count,
            anomaly_count=anomaly_count,
            future_dated_count=future_count,
        )

    # ── Flagging ─────────────────────────────────────────────────────────────
    def _flag(self, bar: Bar, now: datetime) -> Bar:
        flags = set(bar.quality_flags)  # preserve flags attached earlier (bronze)
        if bar.high < max(bar.open, bar.close) or bar.low > min(bar.open, bar.close):
            flags.add(DataQualityFlag.PRICE_ANOMALY)
        if bar.available_time > now + _FUTURE_TOLERANCE:
            flags.add(DataQualityFlag.FUTURE_DATED)
        if now - bar.available_time > self._stale_after:
            flags.add(DataQualityFlag.STALE)
        if not flags:
            flags.add(DataQualityFlag.OK)
        ordered = tuple(sorted(flags, key=lambda flag: flag.value))
        return bar.model_copy(update={"quality_flags": ordered})

    # ── Duplicate handling ───────────────────────────────────────────────────
    @staticmethod
    def _deduplicate(bars: tuple[Bar, ...]) -> tuple[tuple[Bar, ...], int]:
        """Deterministic duplicate resolution.

        Key: ``(instrument_id, timeframe, event_time, source, source_record_id)``.
        Rows are ordered deterministically (key, then ingested_at) and the first
        occurrence wins; later occurrences are kept in silver with a DUPLICATE
        flag (auditable) and are excluded when gold is sealed.
        """
        seen: set[tuple[str, Timeframe, datetime, str, str]] = set()
        result: list[Bar] = []
        duplicates = 0

        def sort_key(bar: Bar) -> tuple[str, Timeframe, datetime, str, str, datetime, bytes]:
            # Content bytes as the final tiebreaker: two identical keys with
            # identical ingested_at still resolve deterministically, independent
            # of input order.
            return (
                bar.instrument_id,
                bar.timeframe,
                bar.event_time,
                bar.source,
                bar.source_record_id,
                bar.ingested_at,
                canonical_bar_bytes(bar),
            )

        for bar in sorted(bars, key=sort_key):
            identity = (
                bar.instrument_id,
                bar.timeframe,
                bar.event_time,
                bar.source,
                bar.source_record_id,
            )
            if identity in seen:
                duplicates += 1
                flags = tuple(
                    sorted((*bar.quality_flags, DataQualityFlag.DUPLICATE), key=lambda f: f.value)
                )
                result.append(bar.model_copy(update={"quality_flags": flags}))
                continue
            seen.add(identity)
            result.append(bar)
        return tuple(result), duplicates

    # ── Missing bar detection ────────────────────────────────────────────────
    @staticmethod
    def _detect_missing_bars(silver: tuple[Bar, ...], now: datetime) -> tuple[BarGap, ...]:
        """Interior gaps per (instrument, timeframe) against the bar grid."""
        gaps: list[BarGap] = []
        grouped: dict[tuple[str, Timeframe], list[Bar]] = {}
        for bar in silver:
            if DataQualityFlag.DUPLICATE in bar.quality_flags:
                continue
            grouped.setdefault((bar.instrument_id, bar.timeframe), []).append(bar)
        for (instrument_id, timeframe), bars in grouped.items():
            ordered = sorted(bars, key=lambda bar: bar.event_time)
            for prev, nxt in pairwise(ordered):
                expected = _next_bar_time(prev.event_time, timeframe)
                while expected < nxt.event_time:
                    gaps.append(
                        BarGap(
                            instrument_id=instrument_id,
                            timeframe=timeframe,
                            expected_time=expected,
                            previous_time=prev.event_time,
                            next_time=nxt.event_time,
                            detected_at=now,
                        )
                    )
                    expected = _next_bar_time(expected, timeframe)
        return tuple(gaps)


def _next_bar_time(moment: datetime, timeframe: Timeframe) -> datetime:
    """Next grid step for a timeframe (calendar-aware for D1/W1/MN1)."""
    if timeframe is Timeframe.D1:
        return moment + timedelta(days=1)
    if timeframe is Timeframe.W1:
        return moment + timedelta(days=7)
    if timeframe is Timeframe.MN1:
        year = moment.year + (1 if moment.month == 12 else 0)
        month = 1 if moment.month == 12 else moment.month + 1
        day = min(moment.day, monthrange(year, month)[1])
        return moment.replace(year=year, month=month, day=day)
    step = TIMEFRAME_STEP.get(timeframe)
    if step is None:
        raise ValueError(f"no grid step for timeframe {timeframe!r}")
    return moment + step
