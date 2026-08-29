"""Tier policy tests: metadata/relevance/temporal policies over ONE store."""

from __future__ import annotations

from datetime import timedelta

import pytest
from adapters.graphiti import TierPolicy
from adapters.graphiti.errors import LayerPolicyError
from adapters.graphiti.schemas import Validity
from core.domain.enums import MemoryLayer
from core.schemas.memory import EntityRef, RelationRef

from factories import FIXED_START
from gt_test_helpers import make_record

T = FIXED_START
policy = TierPolicy()

THESIS = EntityRef(entity_id="thesis-1", entity_type="Thesis", name="EURUSD long")
NEWS = EntityRef(entity_id="news-1", entity_type="NewsEvent", name="NFP surprise")
PLAIN = EntityRef(entity_id="EURUSD", entity_type="Instrument", name="EURUSD")
LEARNED = RelationRef(source="exp-1", relation="LEARNED_FROM", target="trade-1")
FAILED = RelationRef(source="strat-1", relation="FAILED_IN_REGIME", target="regime-1")


class TestClassification:
    def test_open_ended_validity_is_long_term(self) -> None:
        record = make_record(T, validity=Validity(valid_from=T))
        assert policy.classify(record) is MemoryLayer.LONG_TERM

    def test_year_span_is_long_term(self) -> None:
        record = make_record(
            T,
            validity=Validity(valid_from=T, valid_until=T + timedelta(days=400)),
        )
        assert policy.classify(record) is MemoryLayer.LONG_TERM

    def test_structural_hint_with_importance_is_long_term(self) -> None:
        record = make_record(
            T,
            entities=(THESIS,),
            importance=0.9,
            validity=Validity(valid_from=T, valid_until=T + timedelta(days=30)),
        )
        assert policy.classify(record) is MemoryLayer.LONG_TERM

    def test_short_span_with_short_hint_is_short_term(self) -> None:
        record = make_record(
            T,
            entities=(NEWS,),
            importance=0.7,
            validity=Validity(valid_from=T, valid_until=T + timedelta(days=2)),
        )
        assert policy.classify(record) is MemoryLayer.SHORT_TERM

    def test_short_span_with_low_importance_is_short_term(self) -> None:
        record = make_record(
            T,
            entities=(PLAIN,),
            importance=0.4,
            validity=Validity(valid_from=T, valid_until=T + timedelta(days=3)),
        )
        assert policy.classify(record) is MemoryLayer.SHORT_TERM

    def test_middle_ground_is_medium_term(self) -> None:
        record = make_record(
            T,
            entities=(PLAIN,),
            importance=0.7,
            validity=Validity(valid_from=T, valid_until=T + timedelta(days=60)),
        )
        assert policy.classify(record) is MemoryLayer.MEDIUM_TERM

    def test_producer_layer_hint_is_not_authoritative(self) -> None:
        """The declared episode layer cannot override the metadata policy."""
        record = make_record(
            T,
            layer=MemoryLayer.LONG_TERM,
            entities=(NEWS,),
            importance=0.5,
            validity=Validity(valid_from=T, valid_until=T + timedelta(days=1)),
        )
        assert policy.classify(record) is MemoryLayer.SHORT_TERM

    def test_postmortem_relations_make_long_term(self) -> None:
        record = make_record(
            T,
            relations=(LEARNED, FAILED),
            importance=0.8,
            validity=Validity(valid_from=T, valid_until=T + timedelta(days=7)),
        )
        assert policy.classify(record) is MemoryLayer.LONG_TERM


class TestRelevance:
    def test_long_term_does_not_decay(self) -> None:
        record = make_record(T, validity=Validity(valid_from=T))
        assert policy.relevance(record, T + timedelta(days=1000)) == 1.0

    def test_short_term_half_life(self) -> None:
        record = make_record(
            T,
            entities=(NEWS,),
            importance=0.5,
            validity=Validity(valid_from=T - timedelta(hours=1), valid_until=T + timedelta(days=3)),
        )
        assert policy.classify(record) is MemoryLayer.SHORT_TERM
        assert policy.relevance(record, record.available_time) == pytest.approx(1.0)
        assert policy.relevance(
            record, record.available_time + policy.short_half_life
        ) == pytest.approx(0.5)

    def test_relevance_zero_before_availability(self) -> None:
        record = make_record(
            T,
            entities=(NEWS,),
            importance=0.5,
            validity=Validity(valid_from=T - timedelta(hours=1), valid_until=T + timedelta(days=3)),
        )
        assert policy.relevance(record, T - timedelta(hours=2)) == 0.0

    def test_medium_term_decays_slower(self) -> None:
        record = make_record(
            T,
            entities=(PLAIN,),
            importance=0.7,
            validity=Validity(valid_from=T, valid_until=T + timedelta(days=60)),
        )
        assert policy.classify(record) is MemoryLayer.MEDIUM_TERM
        at = T + policy.short_half_life
        assert policy.relevance(record, at) > 0.9  # barely decayed


class TestReach:
    def test_short_term_ages_out(self) -> None:
        record = make_record(
            T,
            entities=(NEWS,),
            importance=0.5,
            validity=Validity(
                valid_from=T - timedelta(hours=1), valid_until=T + timedelta(days=13)
            ),
        )
        assert policy.classify(record) is MemoryLayer.SHORT_TERM
        assert policy.reachable(record, T + timedelta(days=1))
        assert not policy.reachable(record, T + timedelta(days=15))

    def test_medium_term_reaches_a_year(self) -> None:
        record = make_record(
            T,
            entities=(PLAIN,),
            importance=0.7,
            event_time=T,
            available_time=T,
            ingested_at=T,
            validity=Validity(valid_from=T, valid_until=T + timedelta(days=60)),
        )
        assert policy.classify(record) is MemoryLayer.MEDIUM_TERM
        assert policy.reachable(record, T + timedelta(days=365))
        assert not policy.reachable(record, T + timedelta(days=366))

    def test_long_term_always_reachable(self) -> None:
        record = make_record(T, validity=Validity(valid_from=T))
        assert policy.reachable(record, T + timedelta(days=3650))


class TestPolicyValidation:
    def test_overlapping_spans_refused(self) -> None:
        with pytest.raises(LayerPolicyError):
            TierPolicy(short_span_max=timedelta(days=30), medium_span_max=timedelta(days=10))

    def test_nonpositive_half_life_refused(self) -> None:
        with pytest.raises(LayerPolicyError):
            TierPolicy(short_half_life=timedelta(0))
