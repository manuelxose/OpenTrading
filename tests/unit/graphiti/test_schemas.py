"""Envelope contract tests: the seven preserved facts and temporal ordering."""

from __future__ import annotations

from datetime import timedelta

import pytest
from adapters.graphiti.errors import TemporalOrderingError
from adapters.graphiti.schemas import GraphitiConfig, MemoryRecord, SearchWindow, Validity
from pydantic import ValidationError

from factories import FIXED_START, make_memory_episode
from gt_test_helpers import make_record

T = FIXED_START


class TestValidity:
    def test_contains_boundaries(self) -> None:
        v = Validity(valid_from=T, valid_until=T + timedelta(days=1))
        assert v.contains(T)
        assert v.contains(T + timedelta(days=1))  # inclusive end
        assert not v.contains(T - timedelta(seconds=1))
        assert not v.contains(T + timedelta(days=1, seconds=1))

    def test_open_ended_contains_forever(self) -> None:
        v = Validity(valid_from=T)
        assert v.contains(T + timedelta(days=3650))
        assert not v.contains(T - timedelta(seconds=1))

    def test_rejects_inverted_interval(self) -> None:
        with pytest.raises(ValidationError):
            Validity(valid_from=T, valid_until=T - timedelta(seconds=1))

    def test_span_none_when_open_ended(self) -> None:
        assert Validity(valid_from=T).span() is None
        assert Validity(valid_from=T, valid_until=T + timedelta(hours=2)).span() == 7200.0


class TestMemoryRecordEnvelope:
    def test_preserves_all_seven_facts_round_trip(self) -> None:
        episode = make_memory_episode(T)
        record = MemoryRecord.from_episode(
            episode,
            source="tradingagents",
            event_time=T - timedelta(hours=3),
            available_time=T - timedelta(hours=1),
            ingested_at=T,
        )
        assert record.source == "tradingagents"
        assert record.event_time == T - timedelta(hours=3)
        assert record.available_time == T - timedelta(hours=1)
        assert record.ingested_at == T
        assert record.validity.valid_from == episode.valid_from
        assert record.validity.valid_until == episode.valid_until
        assert record.trace_id == episode.trace_id
        assert record.provenance == episode.provenance

        back = record.to_episode()
        assert back.episode_id == episode.episode_id
        assert back.summary == episode.summary
        assert back.entities == episode.entities
        assert back.relations == episode.relations
        assert back.provenance == episode.provenance

    def test_rejects_event_after_availability(self) -> None:
        episode = make_memory_episode(T)
        with pytest.raises(TemporalOrderingError, match="event_time"):
            MemoryRecord.from_episode(
                episode,
                source="feed",
                event_time=T,
                available_time=T - timedelta(seconds=1),
                ingested_at=T,
            )

    def test_rejects_availability_after_ingestion(self) -> None:
        episode = make_memory_episode(T)
        with pytest.raises(TemporalOrderingError, match="available_time"):
            MemoryRecord.from_episode(
                episode,
                source="feed",
                event_time=T - timedelta(hours=1),
                available_time=T,
                ingested_at=T - timedelta(seconds=1),
            )

    def test_allows_simultaneous_timestamps(self) -> None:
        episode = make_memory_episode(T)
        record = MemoryRecord.from_episode(
            episode, source="feed", event_time=T, available_time=T, ingested_at=T
        )
        assert record.observable_at(T)

    def test_rejects_naive_datetimes(self) -> None:
        episode = make_memory_episode(T)
        with pytest.raises(ValueError, match="timezone-aware"):
            MemoryRecord.from_episode(
                episode,
                source="feed",
                event_time=T.replace(tzinfo=None),  # naive
                available_time=T,
                ingested_at=T,
            )

    def test_observable_at(self) -> None:
        record = make_record(T)  # available at T-1h, valid from T-1h
        assert record.observable_at(T)
        assert not record.observable_at(T - timedelta(hours=2))  # before availability
        expired = make_record(T, validity=Validity(valid_from=T, valid_until=T))
        assert not expired.observable_at(T + timedelta(seconds=1))


class TestSearchWindowAndConfig:
    def test_window_validations(self) -> None:
        with pytest.raises(ValidationError):
            SearchWindow(as_of=T, limit=0)
        with pytest.raises(ValidationError):
            SearchWindow(as_of=T, layers=())

    def test_window_defaults(self) -> None:
        window = SearchWindow(as_of=T)
        assert window.layers is None
        assert window.limit == 10
        assert window.min_importance == 0.0

    def test_config_defaults_point_at_dev_falkordb(self) -> None:
        config = GraphitiConfig()
        assert (config.host, config.port) == ("127.0.0.1", 6380)
        assert config.database == "default_db"

    def test_record_rejects_empty_summary(self) -> None:
        record = make_record(T)
        with pytest.raises(ValidationError):
            MemoryRecord.model_validate({**record.model_dump(), "summary": ""})
