"""Clock tests: SystemClock UTC, VirtualClock determinism and monotonicity."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from core.clock.clocks import SystemClock, VirtualClock


class TestSystemClock:
    def test_returns_aware_utc(self) -> None:
        now = SystemClock().now()
        assert now.tzinfo is not None
        assert now.utcoffset() == timedelta(0)


class TestVirtualClock:
    def test_repeated_now_is_identical(self, clock: VirtualClock) -> None:
        assert clock.now() == clock.now()

    def test_advance_moves_forward(self, clock: VirtualClock) -> None:
        before = clock.now()
        after = clock.advance(timedelta(minutes=5))
        assert after == before + timedelta(minutes=5)
        assert clock.now() == after

    def test_deterministic_timeline_across_instances(self) -> None:
        start = datetime(2026, 3, 2, 9, 30, tzinfo=UTC)
        deltas = [timedelta(seconds=1), timedelta(minutes=15), timedelta(hours=2)]

        a = VirtualClock(start)
        b = VirtualClock(start)
        timeline_a = [a.now()]
        timeline_b = [b.now()]
        for delta in deltas:
            timeline_a.append(a.advance(delta))
            timeline_b.append(b.advance(delta))

        assert timeline_a == timeline_b

    def test_deterministic_set(self) -> None:
        start = datetime(2026, 3, 2, 9, 30, tzinfo=UTC)
        target = start + timedelta(days=3, hours=2)
        a = VirtualClock(start)
        b = VirtualClock(start)
        assert a.set(target) == b.set(target) == target

    def test_advance_requires_positive_delta(self, clock: VirtualClock) -> None:
        with pytest.raises(ValueError, match="positive"):
            clock.advance(timedelta(0))
        with pytest.raises(ValueError, match="positive"):
            clock.advance(timedelta(seconds=-1))

    def test_set_backwards_rejected(self, clock: VirtualClock) -> None:
        past = clock.now() - timedelta(seconds=1)
        with pytest.raises(ValueError, match="backwards"):
            clock.set(past)

    def test_set_forward_allowed(self, clock: VirtualClock) -> None:
        future = clock.now() + timedelta(hours=1)
        assert clock.set(future) == future

    def test_naive_start_rejected(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            VirtualClock(datetime(2026, 1, 1))

    def test_start_normalized_to_utc(self) -> None:
        offset = timezone(timedelta(hours=2))
        start = datetime(2026, 1, 1, 12, 0, tzinfo=offset)
        clock = VirtualClock(start)
        assert clock.now() == datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
