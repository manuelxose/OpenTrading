"""Memory service tests: point-in-time retrieval, invalidation, contradictions,
provenance and tiers over the in-memory twin (ADR-0008 Phase 3 semantics)."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import pytest
from adapters.graphiti import Memory
from adapters.graphiti.errors import FutureMemoryLeakageError, OntologyError, TemporalOrderingError
from adapters.graphiti.schemas import Validity
from core.domain.enums import MemoryLayer
from core.schemas.base import Provenance
from core.schemas.memory import EntityRef, MemoryEpisode, RelationRef

from factories import FIXED_START, make_memory_episode
from gt_test_helpers import build_memory, make_record, window_blind_store

T = FIXED_START
HOUR = timedelta(hours=1)
DAY = timedelta(days=1)


class TestIngest:
    def test_ingest_returns_stored_record_with_policy_tier(self) -> None:
        memory = build_memory()
        episode = make_memory_episode(T)
        record = memory.ingest(
            episode, source="tradingagents", event_time=T - HOUR, available_time=T - HOUR
        )
        assert record.episode_id == episode.episode_id
        assert record.source == "tradingagents"
        assert record.ingested_at == T  # virtual clock
        assert isinstance(record.layer, MemoryLayer)

    def test_ingest_rejects_unknown_ontology(self) -> None:
        memory = build_memory()
        bad = make_memory_episode(
            T, entities=[EntityRef(entity_id="X", entity_type="Ticker", name="X")]
        )
        with pytest.raises(OntologyError):
            memory.ingest(bad, source="s", event_time=T, available_time=T)

    def test_ingest_refuses_future_availability(self) -> None:
        memory = build_memory()
        episode = make_memory_episode(T)
        with pytest.raises(TemporalOrderingError):
            memory.ingest(
                episode,
                source="s",
                event_time=T,
                available_time=T + HOUR,
                ingested_at=T,
            )


class TestHistoricalQueries:
    def test_query_at_t_returns_exactly_what_was_known_at_t(self) -> None:
        memory = build_memory()
        old = memory.ingest(
            make_memory_episode(T, summary="friday payroll"),
            source="feed",
            event_time=T - DAY,
            available_time=T - DAY,
            ingested_at=T - DAY,
        )
        recent = memory.ingest(
            make_memory_episode(T, summary="monday open"),
            source="feed",
            event_time=T,
            available_time=T,
            ingested_at=T,
        )
        as_of = T + HOUR
        results = memory.search("payroll open", as_of=as_of, limit=10)
        assert {r.episode_id for r in results} == {old.episode_id, recent.episode_id}

    def test_episode_available_later_is_invisible_earlier(self) -> None:
        memory = build_memory()
        late = make_record(
            T + DAY,
            summary="late-published revision",
            event_time=T - HOUR,
            available_time=T + DAY,
            ingested_at=T + DAY,
        )
        memory = build_memory(late)
        assert memory.search("revision", as_of=T) == ()
        later = memory.search("revision", as_of=T + DAY + HOUR)
        assert [r.summary for r in later] == ["late-published revision"]

    def test_sweep_across_timeline_never_sees_future(self) -> None:
        records = [
            make_record(T + i * DAY, summary=f"day {i}", available_time=T + i * DAY)
            for i in range(5)
        ]
        memory = build_memory(*records)
        for i in range(5):
            as_of = T + i * DAY
            visible = memory.search("day", as_of=as_of, limit=20)
            assert {r.summary for r in visible} == {f"day {j}" for j in range(i + 1)}


class TestTemporalInvalidation:
    def test_expired_episode_is_not_returned(self) -> None:
        expired = make_record(
            T,
            summary="rate cut thesis",
            event_time=T - 2 * DAY,
            available_time=T - DAY,
            ingested_at=T - DAY,
            validity=Validity(valid_from=T - DAY, valid_until=T - HOUR),
        )
        memory = build_memory(expired)
        assert memory.search("thesis", as_of=T) == ()
        assert memory.search("thesis", as_of=T - 2 * HOUR) != ()

    def test_invalidated_then_superseded(self) -> None:
        """INVALIDATES: the old claim stays in memory but stops being valid."""
        old_claim = make_record(
            T,
            summary="FOMC hikes in September",
            validity=Validity(valid_from=T - DAY, valid_until=T + HOUR),
        )
        new_claim = make_record(
            T + HOUR,
            summary="FOMC holds in September",
            relations=(
                RelationRef(source="new-claim", relation="INVALIDATES", target="old-claim"),
            ),
            event_time=T + HOUR,
            available_time=T + HOUR,
            ingested_at=T + HOUR,
        )
        memory = build_memory(old_claim, new_claim)
        before = memory.search("FOMC", as_of=T)
        assert {r.summary for r in before} == {"FOMC hikes in September"}
        after = memory.search("FOMC", as_of=T + 2 * HOUR)
        assert {r.summary for r in after} == {"FOMC holds in September"}

    def test_open_validity_is_never_invalidated_by_time(self) -> None:
        forever = make_record(T, summary="structural lesson", validity=Validity(valid_from=T))
        memory = build_memory(forever)
        assert memory.search("lesson", as_of=T + 365 * DAY) != ()


class TestContradictions:
    def test_both_contradictory_facts_are_preserved_and_returned(self) -> None:
        bullish = make_record(
            T,
            summary="analyst bullish on EURUSD",
            relations=(RelationRef(source="a1", relation="SUPPORTS", target="eurusd-thesis"),),
        )
        bearish = make_record(
            T + HOUR,
            summary="analyst bearish on EURUSD",
            relations=(RelationRef(source="a2", relation="CONTRADICTS", target="eurusd-thesis"),),
            event_time=T + HOUR,
            available_time=T + HOUR,
            ingested_at=T + HOUR,
        )
        memory = build_memory(bullish, bearish)
        results = memory.search("EURUSD", as_of=T + 2 * HOUR)
        assert {r.summary for r in results} == {
            "analyst bullish on EURUSD",
            "analyst bearish on EURUSD",
        }

    def test_contradiction_does_not_hide_the_contradicted_fact(self) -> None:
        supported = make_record(T, summary="factor X works")
        contradicted = make_record(
            T + HOUR,
            summary="factor X failed this regime",
            relations=(RelationRef(source="f", relation="CONTRADICTS", target="factor-x"),),
            event_time=T + HOUR,
            available_time=T + HOUR,
            ingested_at=T + HOUR,
        )
        memory = build_memory(supported, contradicted)
        results = memory.search("factor X", as_of=T + 2 * HOUR)
        assert len(results) == 2  # memory keeps both; it never silently rewrites


class TestProvenance:
    def test_provenance_survives_ingest_store_search(self) -> None:
        provenance = Provenance(
            producer="tradingagents",
            produced_at=T,
            code_version="v0.3.1",
            source_ids={"research_request_id": str(uuid4())},
        )
        episode = make_memory_episode(T, provenance=provenance, trace_id=uuid4())
        memory = build_memory()
        memory.ingest(
            episode,
            source="tradingagents",
            event_time=T - HOUR,
            available_time=T - HOUR,
            ingested_at=T,
        )
        results = memory.search("EURUSD", as_of=T)
        assert len(results) == 1
        returned = results[0]
        assert returned.provenance == provenance
        assert returned.provenance.producer == "tradingagents"
        assert returned.provenance.code_version == "v0.3.1"
        assert returned.trace_id == episode.trace_id

    def test_source_and_timestamps_are_preserved_in_returned_episodes(self) -> None:
        memory = build_memory()
        record = memory.ingest(
            make_memory_episode(T),
            source="macro-feed",
            event_time=T - 3 * HOUR,
            available_time=T - 2 * HOUR,
            ingested_at=T,
        )
        results = memory.search("breakout", as_of=T)
        assert len(results) == 1
        # The envelope facts ride along via the stored record, so inspect the
        # store twin: provenance/source/ingested_at must equal what was ingested.
        assert record.source == "macro-feed"
        assert record.ingested_at == T


class TestTierRetrieval:
    def test_aged_out_short_term_knowledge_is_not_surfaced(self) -> None:
        """Reach binds even when validity still contains as_of: the calendar was
        known 10 days ahead, but short-term reach expires 14 days after it
        became available."""
        news = make_record(
            T,
            summary="scheduled CPI release",
            entities=(EntityRef(entity_id="cpi", entity_type="MacroEvent", name="CPI"),),
            importance=0.5,
            event_time=T - 10 * DAY,
            available_time=T - 10 * DAY,
            ingested_at=T - 10 * DAY,
            validity=Validity(valid_from=T, valid_until=T + 14 * DAY),
        )
        memory = build_memory(news)
        assert memory.search("CPI", as_of=T + 2 * DAY) != ()
        # Age 15 days > 14-day reach, although validity still contains as_of.
        assert memory.search("CPI", as_of=T + 5 * DAY) == ()

    def test_long_term_knowledge_survives_any_horizon(self) -> None:
        lesson = make_record(
            T, summary="lesson: breakouts fail in chop", validity=Validity(valid_from=T)
        )
        memory = build_memory(lesson)
        assert memory.search("breakouts", as_of=T + 1000 * DAY) != ()

    def test_layers_filter_limits_tiers(self) -> None:
        short = make_record(
            T,
            summary="intraday signal",
            entities=(EntityRef(entity_id="s1", entity_type="Signal", name="sig"),),
            importance=0.5,
            validity=Validity(valid_from=T - HOUR, valid_until=T + DAY),
        )
        long = make_record(T, summary="regime map", validity=Validity(valid_from=T))
        memory = build_memory(short, long)
        results = memory.search("", as_of=T, layers=(MemoryLayer.LONG_TERM,), limit=10)
        assert {r.summary for r in results} == {"regime map"}


class TestDefenseInDepth:
    def test_strict_raises_when_backend_leaks_future(self) -> None:
        past = make_record(T, summary="known fact")
        poison = make_record(
            T + DAY,
            summary="tomorrow's fact",
            event_time=T,
            available_time=T + DAY,
            ingested_at=T + DAY,
        )
        memory = Memory(window_blind_store(past, poison))
        with pytest.raises(FutureMemoryLeakageError):
            memory.search("fact", as_of=T, strict=True)

    def test_non_strict_drops_backend_leaks(self) -> None:
        past = make_record(T, summary="known fact")
        poison = make_record(
            T + DAY,
            summary="tomorrow's fact",
            event_time=T,
            available_time=T + DAY,
            ingested_at=T + DAY,
        )
        memory = Memory(window_blind_store(past, poison))
        results = memory.search("fact", as_of=T)
        assert {r.summary for r in results} == {"known fact"}

    def test_naive_as_of_is_rejected(self) -> None:
        memory = build_memory(make_record(T))
        with pytest.raises(ValueError, match="timezone-aware"):
            memory.search("anything", as_of=T.replace(tzinfo=None))


def test_search_returns_domain_episodes() -> None:
    memory = build_memory(make_record(T))
    results = memory.search("breakout", as_of=T)
    assert all(isinstance(result, MemoryEpisode) for result in results)
