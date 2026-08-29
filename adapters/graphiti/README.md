# adapters/graphiti — temporal semantic memory (Phase 3)

Graphiti over FalkorDB implements the temporal trading memory (ADR-0008,
architecture §11). This adapter is the **only** query path to memory, and the
only place allowed to import upstream `graphiti_core` (lazily, inside
`client.py`, version-checked against the pin).

## Layout

| Module       | Role                                                                 |
| ------------ | -------------------------------------------------------------------- |
| `ontology.py`| Frozen trading ontology: 17 entity types, 11 relations (ADR-0008).    |
| `schemas.py` | `MemoryRecord` envelope: `source, event_time, available_time, ingested_at, validity, trace_id, provenance` (+ content, tier, importance). |
| `tiers.py`   | Short/medium/long-term as **policies over one store**: classification from metadata, relevance decay, reach windows. |
| `memory.py`  | `Memory.search(query, as_of=T)` — point-in-time retrieval; `PointInTimeFilter` is the single INV-3 choke point. |
| `store.py`   | `MemoryStore` protocol + deterministic `InMemoryStore` twin.          |
| `client.py`  | `LiveGraphitiStore` — Graphiti + FalkorDriver, upstream import seam.  |
| `pin.py`     | Upstream pin: `graphiti-core[falkordb]==0.29.3` (INV-14).             |

## Point-in-time semantics (INV-3)

Every record carries three timestamps with enforced ordering:

```text
event_time <= available_time <= ingested_at
```

- `event_time` — when the fact happened;
- `available_time` — when the system could first know it (stated explicitly by
  the ingesting component, never inferred);
- `ingested_at` — when it was written to memory (memory clock).

`search(query, as_of=T)` drops every record with `available_time > T` or whose
validity interval does not contain `T`, **after** the store's temporal window
pushdown. The filter in `memory.py` is authoritative; `strict=True` raises
`FutureMemoryLeakageError` if a backend ever returns something unobservable at
`T` (defense in depth). The live store additionally keys Graphiti temporal edges
to `available_time`, so upstream temporal filters align with the invariant, and
resolves search results fail-closed (unknown episodes are dropped).

## Memory tiers

Short-term (hours/days), medium-term (weeks/months), long-term (postmortems,
structural lessons) are **not** three databases: `TierPolicy` classifies each
record from metadata (validity span, importance, entity/relation hints),
decays relevance per tier (half-lives 3d / 45d / none), and bounds reach
(14d / 365d / unlimited). The producer-declared `MemoryEpisode.layer` is
advisory only — the policy is deterministic, so historical simulations replay
identically.

## Live backend (FalkorDB)

```bash
uv pip install "graphiti-core[falkordb]==0.29.3"   # pin in external-lock.yaml
make up                                            # starts FalkorDB on 127.0.0.1:6380
```

The store is configured explicitly (no global settings read):

```python
from adapters.graphiti import GraphitiConfig, LiveGraphitiStore, Memory

store = LiveGraphitiStore(GraphitiConfig(host="127.0.0.1", port=6380, database="default_db"))
memory = Memory(store)
memory.ingest(episode, source="tradingagents", event_time=t0, available_time=t0)
results = memory.search("regime behavior", as_of=simulation_clock.now())
```

An LLM/embedder client is required for semantic extraction and vector search;
without one Graphiti falls back to its default clients from the environment.

## Tests

- `tests/unit/graphiti/` — ontology, envelope, tiers, in-memory store, PIT
  retrieval, temporal invalidation, contradictions, provenance, client pin and
  boundary enforcement;
- `tests/leakage/test_memory_leakage.py` — the Phase 3 DoD: future episodes are
  planted in the store and must be impossible to retrieve at any earlier `as_of`.
