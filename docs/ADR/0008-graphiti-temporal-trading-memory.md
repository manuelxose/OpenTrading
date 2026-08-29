# ADR-0008: Graphiti as the temporal trading memory

- Status: accepted
- Date: 2026-08-26
- Deciders: principal-architect (+ ai-trading-systems + market-data for data-time
  semantics)

## Context

The platform needs a temporal semantic memory that preserves entities, relations,
temporal validity, history, provenance and hybrid search — including in simulated
(point-in-time) contexts. The decision was frozen in `docs/architecture.md` §34.8
("Graphiti será la memoria temporal") and detailed in §11.

## Decision

**Adopt Graphiti as the temporal trading memory**, starting on a FalkorDB backend
(Neo4j only with a clear operational reason, §13). Graphiti physically implements the
three memory layers (§11): short-term (hours/days), medium-term (weeks/months),
long-term (postmortems, structural lessons) — concepts inspired by FinMem, whose runtime
we do not use (§34.9).

The trading ontology is fixed (§11): entities `Instrument, Company, Sector, Currency,
MacroEvent, NewsEvent, Thesis, Signal, MarketRegime, Strategy, Factor, Model, Experiment,
Trade, Position, RiskEvent, DataSource`; relations `SUPPORTS, CONTRADICTS, INVALIDATES,
GENERATED_BY, CAUSED_BY, CORRELATES_WITH, ACTIVE_IN_REGIME, FAILED_IN_REGIME,
EXECUTED_AS, RESULTED_IN, LEARNED_FROM`.

**Point-in-time constraint (INV-3):** retrieval must support
`memory.query(query=..., valid_at=simulation_clock.now())`, and the graph is never
preloaded with the full dataset before a backtest.

## Alternatives considered

- **TradingAgents' append-only decision log as the memory** — rejected: §11 states it is
  useful but insufficient (no temporal graph, provenance, or hybrid search).
- **FinMem runtime directly** — rejected: §34.9 freezes FinMem as inspiration-only;
  its runtime is outdated.
- **Neo4j-first** — rejected: §13 starts with FalkorDB for simplicity.

## Consequences

- Positive: provenance and temporal validity built-in; PIT queries enable leakage-free
  agent backtests.
- Negative: a graph DB is additional infrastructure — scoped by INV-10 (memory lives
  only here, never in Postgres/MinIO).
- Follow-ups: Phase 3 (ontology, ingestion, PIT API) with DoD "a backtest at T never
  retrieves an episode after T".

## Validation

- Frozen decision §34.8; §11 (ontology, layers, example graph); §12/INV-3 (as_of);
  §13 (FalkorDB first).
- INV-11 separation from Graphify (ADR-0009).
- Repo evidence: no memory code yet (PRE-00).
