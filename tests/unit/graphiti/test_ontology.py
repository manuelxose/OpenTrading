"""Ontology contract tests: the frozen trading ontology (ADR-0008, §11)."""

from __future__ import annotations

import pytest
from adapters.graphiti import ENTITY_TYPES, RELATION_TYPES
from adapters.graphiti.errors import OntologyError
from adapters.graphiti.ontology import (
    assert_known_entities,
    assert_known_relations,
    upstream_edge_models,
    upstream_entity_models,
    validate_episode_refs,
)
from core.schemas.memory import EntityRef, RelationRef
from pydantic import BaseModel

REQUIRED_ENTITIES = {
    "Instrument",
    "Company",
    "Currency",
    "Sector",
    "MacroEvent",
    "NewsEvent",
    "Thesis",
    "Signal",
    "MarketRegime",
    "Strategy",
    "Factor",
    "Model",
    "Experiment",
    "Trade",
    "Position",
    "RiskEvent",
    "DataSource",
}

REQUIRED_RELATIONS = {
    "SUPPORTS",
    "CONTRADICTS",
    "INVALIDATES",
    "GENERATED_BY",
    "CAUSED_BY",
    "CORRELATES_WITH",
    "ACTIVE_IN_REGIME",
    "FAILED_IN_REGIME",
    "EXECUTED_AS",
    "RESULTED_IN",
    "LEARNED_FROM",
}


class TestOntologySurface:
    def test_exactly_the_seventeen_entity_types(self) -> None:
        assert {e.value for e in ENTITY_TYPES} == REQUIRED_ENTITIES
        assert len(ENTITY_TYPES) == len(REQUIRED_ENTITIES) == 17

    def test_exactly_the_eleven_relations(self) -> None:
        assert {r.value for r in RELATION_TYPES} == REQUIRED_RELATIONS
        assert len(RELATION_TYPES) == len(REQUIRED_RELATIONS) == 11

    def test_upstream_entity_models_cover_every_type(self) -> None:
        models = upstream_entity_models()
        assert set(models) == REQUIRED_ENTITIES
        assert all(issubclass(model, BaseModel) for model in models.values())

    def test_upstream_edge_models_cover_every_relation(self) -> None:
        models = upstream_edge_models()
        assert set(models) == REQUIRED_RELATIONS
        assert all(issubclass(model, BaseModel) for model in models.values())


class TestOntologyValidation:
    def test_known_entities_pass(self) -> None:
        refs = [
            EntityRef(entity_id="AAPL", entity_type="Instrument", name="Apple"),
            EntityRef(entity_id="cpi-08", entity_type="MacroEvent", name="CPI Aug"),
        ]
        assert_known_entities(refs)  # no exception

    def test_unknown_entity_type_refused(self) -> None:
        with pytest.raises(OntologyError, match="unknown entity type 'Ticker'"):
            assert_known_entities([EntityRef(entity_id="AAPL", entity_type="Ticker", name="Apple")])

    def test_known_relations_pass(self) -> None:
        refs = [
            RelationRef(source="a", relation="SUPPORTS", target="b"),
            RelationRef(source="a", relation="LEARNED_FROM", target="c"),
        ]
        assert_known_relations(refs)  # no exception

    def test_unknown_relation_refused(self) -> None:
        with pytest.raises(OntologyError, match="unknown relation 'SUPPORT'"):
            assert_known_relations([RelationRef(source="a", relation="SUPPORT", target="b")])

    def test_episode_gate_rejects_unknown_relation(self) -> None:
        entities = [EntityRef(entity_id="EURUSD", entity_type="Instrument", name="EURUSD")]
        bad = [RelationRef(source="EURUSD", relation="INFLUENCES", target="thesis-1")]
        with pytest.raises(OntologyError):
            validate_episode_refs(entities, bad)
