"""In-memory store tests: window pushdown semantics and deterministic scoring."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from adapters.graphiti import InMemoryStore
from adapters.graphiti.schemas import SearchWindow, Validity
from core.domain.enums import MemoryLayer

from factories import FIXED_START, make_memory_episode
from gt_test_helpers import make_record

T = FIXED_START
DAY = timedelta(days=1)


class TestStoreSemantics:
    def test_store_is_idempotent_per_episode(self) -> None:
        store = InMemoryStore()
        record = make_record(T)
        store.store(record)
        updated = record.model_copy(update={"summary": "revised summary"})
        store.store(updated)
        assert len(store.all_records()) == 1
        assert store.all_records()[0].summary == "revised summary"

    def test_window_hides_future_availability(self) -> None:
        store = InMemoryStore()
        past = make_record(T, summary="past news")
        future = make_record(
            T,
            summary="future earnings",
            event_time=T - timedelta(hours=1),
            available_time=T + DAY,
            ingested_at=T + DAY,
        )
        store.store(past)
        store.store(future)
        hits = store.search("news earnings", SearchWindow(as_of=T))
        assert {hit.record.summary for hit in hits} == {"past news"}

    def test_window_hides_expired_validity(self) -> None:
        store = InMemoryStore()
        expired = make_record(
            T,
            summary="old regime",
            validity=Validity(valid_from=T - DAY, valid_until=T - timedelta(hours=1)),
        )
        active = make_record(T, summary="current regime")
        store.store(expired)
        store.store(active)
        hits = store.search("regime", SearchWindow(as_of=T))
        assert {hit.record.summary for hit in hits} == {"current regime"}

    def test_layer_and_importance_filters(self) -> None:
        store = InMemoryStore()
        store.store(make_record(T, summary="short news", layer=MemoryLayer.SHORT_TERM))
        store.store(
            make_record(T, summary="long lesson", layer=MemoryLayer.LONG_TERM, importance=0.9)
        )
        hits = store.search(
            "news lesson",
            SearchWindow(as_of=T, layers=(MemoryLayer.LONG_TERM,), min_importance=0.5),
        )
        assert {hit.record.summary for hit in hits} == {"long lesson"}

    def test_limit_truncates(self) -> None:
        store = InMemoryStore()
        for i in range(5):
            store.store(make_record(T + timedelta(minutes=i), summary=f"event {i}"))
        hits = store.search("event", SearchWindow(as_of=T + DAY, limit=3))
        assert len(hits) == 3

    def test_matching_summary_ranks_first(self) -> None:
        store = InMemoryStore()
        match = make_record(T, summary="momentum factor breakdown")
        other = make_record(T + timedelta(minutes=1), summary="unrelated macro data")
        store.store(match)
        store.store(other)
        hits = store.search("momentum factor", SearchWindow(as_of=T + DAY, limit=10))
        assert hits[0].record.summary == "momentum factor breakdown"

    def test_empty_query_orders_by_importance(self) -> None:
        store = InMemoryStore()
        low = make_record(T, summary="a", importance=0.2)
        high = make_record(T + timedelta(minutes=1), summary="b", importance=0.9)
        store.store(low)
        store.store(high)
        hits = store.search("", SearchWindow(as_of=T + DAY, limit=10))
        assert [hit.record.summary for hit in hits] == ["b", "a"]

    def test_ordering_is_deterministic(self) -> None:
        store = InMemoryStore()
        record = make_record(T, summary="same importance")
        twin = make_record(
            T,
            summary="same importance",
            episode=make_memory_episode(T + timedelta(minutes=1)),
        )
        store.store(record)
        store.store(twin)
        first = store.search("same importance", SearchWindow(as_of=T + DAY, limit=10))
        second = store.search("same importance", SearchWindow(as_of=T + DAY, limit=10))
        assert [h.record.episode_id for h in first] == [h.record.episode_id for h in second]

    def test_close_is_a_noop(self) -> None:
        store = InMemoryStore(make_record(T))
        store.close()
        assert len(store.all_records()) == 1


def test_episode_ids_are_stable_keys() -> None:
    store = InMemoryStore()
    episode_id = uuid4()
    record = make_record(T, episode_id=episode_id)
    store.store(record)
    assert store.all_records()[0].episode_id == episode_id
