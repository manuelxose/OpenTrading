"""Memory leakage tests: future episodes must be impossible to retrieve (INV-3).

Phase 3 Definition of Done:

**An analysis at time T can query what the system knew at T, without seeing
what it learned after T.**

These tests deliberately plant future information into the memory store and
prove that the repository and the public search API never surface it — the
point-in-time filter cannot be bypassed, the tier policy adds no alternative
path, and `strict=True` raises a typed error when a backend misbehaves.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from adapters.graphiti import InMemoryStore, Memory, PointInTimeFilter
from adapters.graphiti.errors import FutureMemoryLeakageError
from adapters.graphiti.schemas import Validity
from core.clock.clocks import VirtualClock

from factories import FIXED_START
from gt_test_helpers import build_memory, make_record, window_blind_store

T = FIXED_START
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)

# Poison records planted into the store: each one represents information the
# system must NOT be able to see at an early as_of.
POISON_FUTURE_AVAILABILITY = "poison-future-availability"
POISON_FUTURE_VALIDITY = "poison-future-validity"
POISON_FUTURE_EVENT = "poison-future-event"


def _build_memory_with_poison() -> Memory:
    """One legitimate episode plus three poison episodes in a single store."""
    known = make_record(T, summary="known at T")
    late_availability = make_record(
        T + DAY,
        summary=POISON_FUTURE_AVAILABILITY,
        event_time=T,
        available_time=T + DAY,
        ingested_at=T + DAY,
    )
    future_validity = make_record(
        T,
        summary=POISON_FUTURE_VALIDITY,
        validity=Validity(valid_from=T + DAY),
    )
    future_event = make_record(
        T + 2 * DAY,
        summary=POISON_FUTURE_EVENT,
        event_time=T + 2 * DAY,
        available_time=T + 2 * DAY,
        ingested_at=T + 2 * DAY,
    )
    return build_memory(known, late_availability, future_validity, future_event)


class TestMemoryLeakage:
    def test_future_episodes_never_surface_before_their_time(self) -> None:
        memory = _build_memory_with_poison()
        summaries = {r.summary for r in memory.search("", as_of=T + HOUR, limit=50)}
        assert summaries == {"known at T"}

    def test_every_returned_episode_satisfies_the_invariant(self) -> None:
        """Each poison may only appear at-or-after the moment it became
        available (or valid) — never one second earlier."""
        memory = _build_memory_with_poison()
        expectations = [
            {"known at T"},
            {"known at T", POISON_FUTURE_VALIDITY, POISON_FUTURE_AVAILABILITY},
            {
                "known at T",
                POISON_FUTURE_VALIDITY,
                POISON_FUTURE_AVAILABILITY,
                POISON_FUTURE_EVENT,
            },
            {
                "known at T",
                POISON_FUTURE_VALIDITY,
                POISON_FUTURE_AVAILABILITY,
                POISON_FUTURE_EVENT,
            },
        ]
        for day, expected in enumerate(expectations):
            as_of = T + day * DAY
            actual = {r.summary for r in memory.search("", as_of=as_of, limit=50)}
            assert actual == expected, f"mismatch at day {day}"

    def test_filter_keeps_only_observable_records(self) -> None:
        """The choke point itself rejects every planted poison at early as_of."""
        known = make_record(T, summary="known at T")
        poisons = [
            make_record(
                T + DAY,
                summary=POISON_FUTURE_AVAILABILITY,
                event_time=T,
                available_time=T + DAY,
                ingested_at=T + DAY,
            ),
            make_record(T, summary=POISON_FUTURE_VALIDITY, validity=Validity(valid_from=T + DAY)),
        ]
        store = InMemoryStore([known, *poisons])
        pit = PointInTimeFilter(T + HOUR)
        kept = {r.summary for r in store.all_records() if pit.keep(r)}
        assert kept == {"known at T"}

    def test_poison_records_are_physically_present_but_invisible(self) -> None:
        """The store truly contains future data (poison planted) yet the public
        API cannot return it."""
        store = InMemoryStore()
        memory = Memory(store, clock=VirtualClock(T))
        known = make_record(T, summary="known at T")
        poison = make_record(
            T + DAY,
            summary=POISON_FUTURE_AVAILABILITY,
            event_time=T,
            available_time=T + DAY,
            ingested_at=T + DAY,
        )
        memory.ingest(
            known.to_episode(),
            source=known.source,
            event_time=known.event_time,
            available_time=known.available_time,
            ingested_at=known.ingested_at,
        )
        memory.ingest(
            poison.to_episode(),
            source=poison.source,
            event_time=poison.event_time,
            available_time=poison.available_time,
            ingested_at=poison.ingested_at,
        )
        stored = {r.summary for r in store.all_records()}
        assert POISON_FUTURE_AVAILABILITY in stored  # truly planted

        visible = memory.search("", as_of=T, limit=50)
        assert {r.summary for r in visible} == {"known at T"}

    def test_analysis_at_t_reconstructs_exactly_knowledge_at_t(self) -> None:
        """DoD in one assertion: a timeline sweep where results at T equal the
        set of episodes with available_time <= T (and validity containing T)."""
        episodes = [make_record(T + i * DAY, summary=f"day-{i}") for i in range(4)]
        memory = build_memory(*episodes)
        for i in range(4):
            as_of = T + i * DAY
            expected = {r.summary for r in episodes if r.observable_at(as_of)}
            actual = {r.summary for r in memory.search("", as_of=as_of, limit=50)}
            assert actual == expected, f"mismatch at {as_of.isoformat()}"


class TestDefenseInDepth:
    def test_strict_guard_raises_on_backend_leakage(self) -> None:
        known = make_record(T, summary="known at T")
        poison = make_record(
            T + DAY,
            summary="poison",
            event_time=T,
            available_time=T + DAY,
            ingested_at=T + DAY,
        )
        memory = Memory(window_blind_store(known, poison))
        with pytest.raises(FutureMemoryLeakageError):
            memory.search("", as_of=T, strict=True)

    def test_filter_alone_drops_violating_records(self) -> None:
        pit = PointInTimeFilter(T)
        future = make_record(
            T + DAY,
            event_time=T,
            available_time=T + DAY,
            ingested_at=T + DAY,
        )
        from adapters.graphiti.schemas import MemoryHit

        assert pit.apply((MemoryHit(record=future, score=1.0),)) == ()
        assert pit.dropped((MemoryHit(record=future, score=1.0),)) != ()

    def test_naive_as_of_never_reaches_the_filter(self) -> None:
        memory = build_memory(make_record(T))
        with pytest.raises(ValueError):
            memory.search("", as_of=T.replace(tzinfo=None))


def test_invariant_holds_for_every_as_of_in_a_sweep() -> None:
    """Sweep as_of through the whole timeline against a backend that reports
    everything: only availability gates what the analysis can see."""
    known = make_record(T, summary="known at T")
    future = make_record(
        T + DAY,
        summary="future",
        event_time=T,
        available_time=T + DAY,
        ingested_at=T + DAY,
    )
    memory = Memory(window_blind_store(known, future))
    for hours in range(48):
        as_of = T + hours * HOUR
        results = memory.search("", as_of=as_of, limit=50)
        if as_of < T + DAY:
            assert {r.summary for r in results} == {"known at T"}
        else:
            assert {r.summary for r in results} == {"known at T", "future"}
