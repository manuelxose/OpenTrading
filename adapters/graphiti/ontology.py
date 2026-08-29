"""Frozen trading ontology (ADR-0008, architecture §11).

Seventeen entity types and eleven relations. The ontology is validated at the
adapter boundary: an episode that references an unknown entity type or relation
is refused before it reaches the graph store.

The upstream extraction models (:func:`upstream_entity_models`,
:func:`upstream_edge_models`) are the *only* place the ontology is described to
Graphiti's LLM extractor — one lightweight Pydantic model per type, built here
so the live client never hardcodes the ontology twice.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from core.schemas.memory import EntityRef, RelationRef
from pydantic import BaseModel, ConfigDict, Field, create_model

from adapters.graphiti.errors import OntologyError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Iterable

__all__ = [
    "ENTITY_TYPES",
    "ENTITY_TYPES_SET",
    "RELATION_TYPES",
    "RELATION_TYPES_SET",
    "EntityType",
    "RelationType",
    "assert_known_entities",
    "assert_known_relations",
    "upstream_edge_models",
    "upstream_entity_models",
    "validate_episode_refs",
]


class EntityType(StrEnum):
    """The seventeen entity types of the trading ontology (architecture §11)."""

    INSTRUMENT = "Instrument"
    COMPANY = "Company"
    CURRENCY = "Currency"
    SECTOR = "Sector"
    MACRO_EVENT = "MacroEvent"
    NEWS_EVENT = "NewsEvent"
    THESIS = "Thesis"
    SIGNAL = "Signal"
    MARKET_REGIME = "MarketRegime"
    STRATEGY = "Strategy"
    FACTOR = "Factor"
    MODEL = "Model"
    EXPERIMENT = "Experiment"
    TRADE = "Trade"
    POSITION = "Position"
    RISK_EVENT = "RiskEvent"
    DATA_SOURCE = "DataSource"


class RelationType(StrEnum):
    """The eleven relations of the trading ontology (architecture §11)."""

    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    INVALIDATES = "INVALIDATES"
    GENERATED_BY = "GENERATED_BY"
    CAUSED_BY = "CAUSED_BY"
    CORRELATES_WITH = "CORRELATES_WITH"
    ACTIVE_IN_REGIME = "ACTIVE_IN_REGIME"
    FAILED_IN_REGIME = "FAILED_IN_REGIME"
    EXECUTED_AS = "EXECUTED_AS"
    RESULTED_IN = "RESULTED_IN"
    LEARNED_FROM = "LEARNED_FROM"


ENTITY_TYPES: tuple[EntityType, ...] = tuple(EntityType)
RELATION_TYPES: tuple[RelationType, ...] = tuple(RelationType)

ENTITY_TYPES_SET: frozenset[str] = frozenset(e.value for e in ENTITY_TYPES)
RELATION_TYPES_SET: frozenset[str] = frozenset(r.value for r in RELATION_TYPES)


def assert_known_entities(refs: Iterable[EntityRef]) -> None:
    """Refuse any entity reference whose type is not in the frozen ontology."""
    for ref in refs:
        if ref.entity_type not in ENTITY_TYPES_SET:
            raise OntologyError(
                f"unknown entity type {ref.entity_type!r} for entity {ref.entity_id!r}; "
                f"ontology allows: {sorted(ENTITY_TYPES_SET)}"
            )


def assert_known_relations(refs: Iterable[RelationRef]) -> None:
    """Refuse any relation not in the frozen ontology."""
    for ref in refs:
        if ref.relation not in RELATION_TYPES_SET:
            raise OntologyError(
                f"unknown relation {ref.relation!r} on {ref.source!r} -> {ref.target!r}; "
                f"ontology allows: {sorted(RELATION_TYPES_SET)}"
            )


def validate_episode_refs(entities: Iterable[EntityRef], relations: Iterable[RelationRef]) -> None:
    """Ontology gate for a whole episode: every entity type and relation must be known."""
    assert_known_entities(entities)
    assert_known_relations(relations)


def _extraction_model(name: str) -> type[BaseModel]:
    """One minimal extraction model per ontology type for Graphiti's typed extractor."""
    return create_model(
        name,
        __config__=ConfigDict(extra="allow"),
        name=(str, Field(description=f"Name of the {name}")),
        description=(str, Field(default="", description=f"One-line description of the {name}")),
    )


_ENTITY_MODELS: dict[str, type[BaseModel]] = {
    t.value: _extraction_model(t.value) for t in ENTITY_TYPES
}
_EDGE_MODELS: dict[str, type[BaseModel]] = {
    r.value: _extraction_model(r.value) for r in RELATION_TYPES
}


def upstream_entity_models() -> dict[str, type[BaseModel]]:
    """Entity-type extraction models keyed by ontology name (Graphiti ``entity_types``)."""
    return dict(_ENTITY_MODELS)


def upstream_edge_models() -> dict[str, type[BaseModel]]:
    """Relation extraction models keyed by ontology name (Graphiti ``edge_types``)."""
    return dict(_EDGE_MODELS)
