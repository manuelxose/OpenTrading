# ADR-0017: Point-in-time market data semantics (medallion pipeline)

- Status: accepted
- Date: 2026-08-26
- Deciders: principal-architect (+ market-data owner, + quant-research + verification as mandatory reviewers for the data-time change class)

## Context

Phase 1 (Data Platform) must deliver market data that can never leak future
information into simulated contexts (INV-3: "during a backtest at time T nothing
posterior to T may be visible"). ADR-0011 froze MinIO + Parquet with the
medallion layout `/raw → /bronze → /silver → /gold`; ADR-0010 froze PostgreSQL
as the metadata/catalog/state store. What remained undecided is the exact
temporal semantics — how each record is timestamped, how `as_of` filtering is
enforced, and how reproducibility is proven.

## Decision

Every market data record carries **three** distinct timestamps:

- `event_time` — when the market event happened (bar open time);
- `available_time` — when the event became knowable to the platform. If the
  source does not declare one, it is inferred as the ingestion instant
  (conservative: never earlier than reality) and the row is flagged
  `AVAILABLE_TIME_INFERRED`;
- `ingested_at` — pipeline clock instant at ingestion.

The absolute invariant is: **no record with `available_time > as_of` (nor
`event_time > as_of`) may appear in any query result or `MarketSnapshot`.**

- `PointInTimeFilter` (`adapters/market_data/repository.py`) is the single
  choke point every read path goes through; there is no unfiltered public read.
- `MarketSnapshot` generation requires an explicit `as_of` and an explicit
  sealed `dataset_version` (the HTTP API rejects requests without both).
- Gold dataset versions are immutable: sealing computes one deterministic
  SHA-256 `dataset_hash` over canonically ordered rows and writes partition
  checksums plus a `_manifest.json`; the repository re-verifies checksums and
  the dataset hash on every read, so tampering is detected, not silently served.
- OHLCV ships first; fundamentals, macro and news reuse the same flow by adding
  payload mappers per `MarketDataClass`, not new layers.

Reproducibility (DoD): `(instrument X, dataset version Y, as_of T)` always
produces the exact same `MarketSnapshot` hash. `snapshot_data_hash` covers only
the data fields — `produced_at`, `provenance`, `trace_id` are excluded.

## Alternatives considered

- **Source timestamp only** — rejected: a source that publishes bars late (or
  revises values) would leak posterior information into early `as_of` queries.
- **Filtering only in backtest engines** — rejected: every future consumer
  (TradingAgents, Graphiti, Nautilus, research) would have to re-implement the
  invariant; a single repository-level filter is auditable and impossible to
  forget.
- **Inferring `available_time` from `event_time`** — rejected: that assumes
  immediate publication and silently reintroduces look-ahead.
- **Mutating sealed datasets (append-only versions)** — rejected: immutability
  is what makes `(dataset_version, as_of)` hashes reproducible; new data always
  creates a new version.

## Consequences

- Positive: single auditable enforcement point for INV-3; deterministic dataset
  and snapshot hashes; tamper-evident gold; leakage tests that fail the build.
- Negative: three timestamps per row increase storage slightly; re-sealing is
  impossible by design (new version required) — documented operator behavior.
- Follow-ups: Phase 2+ consumers (TradingAgents, Graphiti, Nautilus) must take
  `MarketSnapshot` through this repository only; per-source staleness
  thresholds are configurable (`OT_MARKET_DATA_STALE_AFTER_SECONDS`).

## Validation

- `tests/leakage/test_point_in_time_leakage.py` — deliberately inserts
  future-dated/available data and proves the repository and the HTTP API
  exclude it; proves `(X, Y, T)` snapshot hash reproducibility across
  independent platform instances.
- `tests/unit/market_data/*` — normalization, quality flags, dedup, gap
  detection, hashing, storage codecs, pipeline and repository behavior.
- `tests/integration/test_market_data_integration.py` — full path against real
  MinIO + PostgreSQL (OT_INTEGRATION).
- `docs/architecture/PHASE1_DATA_PLATFORM.md` — implementation record.
