"""Unit tests: quality flags, duplicate handling, missing-bar detection."""

from __future__ import annotations

from datetime import timedelta

from adapters.market_data.quality import DataQualityEngine
from core.clock.clocks import VirtualClock
from core.domain.enums import DataQualityFlag, Timeframe

from factories import FIXED_START, make_bar


def _engine() -> DataQualityEngine:
    return DataQualityEngine(stale_after=timedelta(hours=1))


class TestFlags:
    def test_clean_bar_gets_ok(self) -> None:
        bar = make_bar(FIXED_START)
        clock = VirtualClock(FIXED_START)
        (flagged,) = _engine().process((bar,), clock).silver_bars
        assert flagged.quality_flags == (DataQualityFlag.OK,)

    def test_price_anomaly_flagged(self) -> None:
        # high(1.08002) < close(1.08005) → anomaly; low <= high still holds.
        bar = make_bar(FIXED_START, high="1.08002")
        clock = VirtualClock(FIXED_START)
        (flagged,) = _engine().process((bar,), clock).silver_bars
        assert DataQualityFlag.PRICE_ANOMALY in flagged.quality_flags
        assert DataQualityFlag.OK not in flagged.quality_flags

    def test_stale_flagged(self) -> None:
        stale = make_bar(FIXED_START, available_time=FIXED_START - timedelta(hours=3))
        clock = VirtualClock(FIXED_START)
        (flagged,) = _engine().process((stale,), clock).silver_bars
        assert DataQualityFlag.STALE in flagged.quality_flags

    def test_future_dated_flagged(self) -> None:
        future = make_bar(FIXED_START, available_time=FIXED_START + timedelta(minutes=10))
        clock = VirtualClock(FIXED_START)
        (flagged,) = _engine().process((future,), clock).silver_bars
        assert DataQualityFlag.FUTURE_DATED in flagged.quality_flags

    def test_existing_flags_preserved(self) -> None:
        bar = make_bar(FIXED_START, quality_flags=(DataQualityFlag.AVAILABLE_TIME_INFERRED,))
        clock = VirtualClock(FIXED_START)
        (flagged,) = _engine().process((bar,), clock).silver_bars
        assert DataQualityFlag.AVAILABLE_TIME_INFERRED in flagged.quality_flags


class TestDuplicates:
    def test_first_occurrence_wins_deterministically(self) -> None:
        first = make_bar(FIXED_START, source_record_id="dup")
        second = make_bar(FIXED_START, source_record_id="dup", close="9.99999")
        clock = VirtualClock(FIXED_START)
        outcome = _engine().process((second, first), clock)  # shuffled input
        kept = [
            bar for bar in outcome.silver_bars if DataQualityFlag.DUPLICATE not in bar.quality_flags
        ]
        assert len(kept) == 1
        # Content tiebreaker: canonical bytes order puts the lower close first,
        # regardless of input order (deterministic duplicate resolution).
        assert kept[0].close == first.close
        assert outcome.duplicate_count == 1

    def test_distinct_records_not_duplicates(self) -> None:
        a = make_bar(FIXED_START, source_record_id="a")
        b = make_bar(
            FIXED_START, source_record_id="b", event_time=FIXED_START + timedelta(minutes=1)
        )
        outcome = _engine().process((a, b), VirtualClock(FIXED_START))
        assert outcome.duplicate_count == 0


class TestMissingBars:
    def test_interior_gap_detected(self) -> None:
        clock = VirtualClock(FIXED_START)
        bars = (
            make_bar(FIXED_START, source_record_id="b0"),
            make_bar(FIXED_START + timedelta(minutes=3), source_record_id="b3"),
        )
        outcome = _engine().process(bars, clock)
        assert len(outcome.gaps) == 2  # +1 and +2 minutes
        assert [gap.expected_time for gap in outcome.gaps] == [
            FIXED_START + timedelta(minutes=1),
            FIXED_START + timedelta(minutes=2),
        ]

    def test_no_gap_when_contiguous(self) -> None:
        clock = VirtualClock(FIXED_START)
        bars = (
            make_bar(FIXED_START, source_record_id="b0"),
            make_bar(FIXED_START + timedelta(minutes=1), source_record_id="b1"),
        )
        outcome = _engine().process(bars, clock)
        assert outcome.gaps == ()

    def test_daily_grid_uses_calendar_steps(self) -> None:
        clock = VirtualClock(FIXED_START)
        bars = (
            make_bar(FIXED_START, timeframe=Timeframe.D1, source_record_id="d0"),
            make_bar(
                FIXED_START + timedelta(days=3),
                timeframe=Timeframe.D1,
                source_record_id="d3",
            ),
        )
        outcome = _engine().process(bars, clock)
        assert len(outcome.gaps) == 2
