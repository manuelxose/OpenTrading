"""Live store tests over the fake upstream seam (no FalkorDB required)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from adapters.graphiti import GraphitiConfig, LiveGraphitiStore, Memory
from adapters.graphiti.errors import (
    GraphitiIngestError,
    GraphitiSearchError,
    GraphitiUnavailableError,
    GraphitiVersionError,
)
from adapters.graphiti.pin import UPSTREAM_DISTRIBUTION, UPSTREAM_VERSION

from factories import FIXED_START
from gt_test_helpers import FakeEdge, FakeUpstream, make_record

T = FIXED_START
HOUR = timedelta(hours=1)


class TestPin:
    def test_missing_upstream_raises_typed_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("adapters.graphiti.client._installed_version", lambda: None)
        with pytest.raises(GraphitiUnavailableError, match=UPSTREAM_DISTRIBUTION):
            LiveGraphitiStore()

    def test_wrong_version_raises_version_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("adapters.graphiti.client._installed_version", lambda: "0.0.1")
        with pytest.raises(GraphitiVersionError, match=r"0\.0\.1"):
            LiveGraphitiStore()

    def test_pinned_version_is_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("adapters.graphiti.client._installed_version", lambda: UPSTREAM_VERSION)
        store = LiveGraphitiStore()
        store.close()
        assert store.envelopes == {}

    def test_check_version_can_be_skipped(self) -> None:
        store = LiveGraphitiStore(check_version=False)
        store.close()


class TestStoreWrite:
    def test_add_episode_keys_graph_time_to_available_time(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        upstream = FakeUpstream()
        monkeypatch.setattr("adapters.graphiti.client._installed_version", lambda: UPSTREAM_VERSION)
        monkeypatch.setattr("adapters.graphiti.client._load_upstream", upstream)

        record = make_record(T, source="macro-feed")
        store = LiveGraphitiStore(GraphitiConfig(host="falkor.internal", port=6381))
        store.store(record)

        assert upstream.driver_kwargs == {
            "host": "falkor.internal",
            "port": 6381,
            "username": None,
            "password": None,
            "database": "default_db",
        }
        assert len(upstream.graph.added) == 1
        call = upstream.graph.added[0]
        assert call["reference_time"] == record.available_time  # PIT alignment
        assert call["source_description"] == "macro-feed"
        assert call["uuid"] == str(record.episode_id)
        assert "__ENVELOPE__" in call["episode_body"]
        assert call["episode_body"].startswith(record.summary)
        assert call["entity_types"]  # ontology extraction models passed
        assert call["edge_types"]

    def test_envelope_index_is_updated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        upstream = FakeUpstream()
        monkeypatch.setattr("adapters.graphiti.client._installed_version", lambda: UPSTREAM_VERSION)
        monkeypatch.setattr("adapters.graphiti.client._load_upstream", upstream)
        record = make_record(T)
        store = LiveGraphitiStore(check_version=False)
        store.store(record)
        assert store.envelopes[record.episode_id] == record

    def test_upstream_failure_is_translated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        upstream = FakeUpstream()
        monkeypatch.setattr("adapters.graphiti.client._load_upstream", upstream)

        def boom(**kwargs: object) -> None:
            raise RuntimeError("falkor down")

        upstream.graph.add_episode = boom  # type: ignore[method-assign]
        store = LiveGraphitiStore(check_version=False)
        with pytest.raises(GraphitiIngestError, match="add_episode"):
            store.store(make_record(T))


class TestSearchResolution:
    def test_edges_resolve_through_known_envelopes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        upstream = FakeUpstream()
        monkeypatch.setattr("adapters.graphiti.client._load_upstream", upstream)
        record = make_record(T)
        store = LiveGraphitiStore(check_version=False)
        store.store(record)

        upstream.graph.search_results = [FakeEdge(episodes=[str(record.episode_id)])]
        from adapters.graphiti.schemas import SearchWindow

        hits = store.search("anything", SearchWindow(as_of=T + HOUR))
        assert [hit.record.episode_id for hit in hits] == [record.episode_id]

    def test_unknown_episodes_are_dropped_fail_closed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        upstream = FakeUpstream()
        monkeypatch.setattr("adapters.graphiti.client._load_upstream", upstream)
        store = LiveGraphitiStore(check_version=False)
        store.store(make_record(T))

        upstream.graph.search_results = [
            FakeEdge(episodes=["11111111-1111-1111-1111-111111111111"]),
            FakeEdge(episodes=["not-a-uuid"]),
        ]
        from adapters.graphiti.schemas import SearchWindow

        assert store.search("anything", SearchWindow(as_of=T)) == ()

    def test_temporal_pushdown_uses_as_of(self, monkeypatch: pytest.MonkeyPatch) -> None:
        upstream = FakeUpstream()
        monkeypatch.setattr("adapters.graphiti.client._load_upstream", upstream)
        store = LiveGraphitiStore(check_version=False)
        upstream.graph.search_results = []

        from adapters.graphiti.schemas import SearchWindow

        store.search("query", SearchWindow(as_of=T))
        filters = upstream.filter_kwargs["valid_at"]
        assert len(filters) == 1
        assert filters[0].date == T
        assert str(filters[0].comparison_operator) == "<="

    def test_upstream_search_failure_is_translated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        upstream = FakeUpstream()
        monkeypatch.setattr("adapters.graphiti.client._load_upstream", upstream)

        def boom(query: str, num_results: int = 10, search_filter: object = None) -> list[object]:
            raise RuntimeError("falkor down")

        upstream.graph.search = boom  # type: ignore[method-assign]
        store = LiveGraphitiStore(check_version=False)

        from adapters.graphiti.schemas import SearchWindow

        with pytest.raises(GraphitiSearchError, match="search"):
            store.search("query", SearchWindow(as_of=T))

    def test_close_is_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        upstream = FakeUpstream()
        monkeypatch.setattr("adapters.graphiti.client._load_upstream", upstream)
        store = LiveGraphitiStore(check_version=False)
        store.close()
        store.close()
        assert upstream.graph.closed is False  # graph never constructed


class TestMemoryOverLiveStore:
    def test_memory_repository_filters_live_hits(self, monkeypatch: pytest.MonkeyPatch) -> None:
        upstream = FakeUpstream()
        monkeypatch.setattr("adapters.graphiti.client._load_upstream", upstream)
        store = LiveGraphitiStore(check_version=False)
        known = make_record(T, summary="known fact")
        poison = make_record(
            T + HOUR,
            summary="future fact",
            event_time=T,
            available_time=T + HOUR,
            ingested_at=T + HOUR,
        )
        store.store(known)
        store.store(poison)

        # The backend returns BOTH edges (bad backend behavior); the repository
        # must drop the future one.
        upstream.graph.search_results = [
            FakeEdge(episodes=[str(known.episode_id), str(poison.episode_id)])
        ]
        memory = Memory(store)
        results = memory.search("fact", as_of=T)
        assert [r.summary for r in results] == ["known fact"]
