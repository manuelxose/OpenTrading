"""Graphiti adapter — Phase 3, temporal trading memory (ADR-0008, INV-3, INV-11).

Temporal semantic memory over a FalkorDB-backed Graphiti store:

- :mod:`adapters.graphiti.ontology` — the frozen trading ontology
  (17 entity types, 11 relations) and upstream extraction models;
- :mod:`adapters.graphiti.schemas` — the storage envelope: every item preserves
  ``source, event_time, available_time, ingested_at, validity, trace_id,
  provenance``;
- :mod:`adapters.graphiti.tiers` — short/medium/long-term tiers as metadata,
  relevance and temporal policies over one store (never three databases);
- :mod:`adapters.graphiti.memory` — :class:`~adapters.graphiti.memory.Memory`
  with point-in-time retrieval ``search(query, as_of=T)``; the single INV-3
  choke point (:class:`~adapters.graphiti.memory.PointInTimeFilter`);
- :mod:`adapters.graphiti.store` — backend protocol and the deterministic
  in-memory twin;
- :mod:`adapters.graphiti.client` — live Graphiti-over-FalkorDB store (the only
  module allowed to import upstream, lazily, version-checked against the pin).

Phase 3 DoD: an analysis at time T queries what the system knew at T, never
what it learned after T.
"""

from adapters.graphiti.client import LiveGraphitiStore
from adapters.graphiti.memory import Memory, PointInTimeFilter
from adapters.graphiti.ontology import (
    ENTITY_TYPES,
    RELATION_TYPES,
    EntityType,
    RelationType,
)
from adapters.graphiti.schemas import (
    GraphitiConfig,
    MemoryHit,
    MemoryRecord,
    SearchWindow,
    Validity,
)
from adapters.graphiti.store import InMemoryStore, MemoryStore
from adapters.graphiti.tiers import TierPolicy

__all__ = [
    "ENTITY_TYPES",
    "RELATION_TYPES",
    "EntityType",
    "GraphitiConfig",
    "InMemoryStore",
    "LiveGraphitiStore",
    "Memory",
    "MemoryHit",
    "MemoryRecord",
    "MemoryStore",
    "PointInTimeFilter",
    "RelationType",
    "SearchWindow",
    "TierPolicy",
    "Validity",
]
