# ADR-0011: MinIO + Parquet for large historical datasets

- Status: accepted
- Date: 2026-08-26
- Deciders: principal-architect (+ market-data + quant-research for data-time class)

## Context

Heavy historical data (ticks, bars, fundamentals, news, features, backtest results) does
not belong in a transactional DB. The decision was frozen in
`docs/architecture.md` §34.13 ("Parquet/MinIO serán la fuente histórica pesada") and
detailed in §13.

## Decision

**MinIO (S3-compatible object storage) with Parquet files is the heavy-history store**,
organized in medallion layers (§13):

```text
/raw → /bronze → /silver → /gold
```

Contents: ticks, bars, fundamentals, macro, news datasets, features, model datasets,
backtest results, artifacts. A Parquet catalog (in `data/catalogs`, §27) makes datasets
discoverable, and point-in-time snapshots (Phase 1) are derived from these layers.

## Alternatives considered

- **Heavy data in PostgreSQL** — rejected: INV-10 separation by purpose; row-store cost
  for billions of ticks/bars is prohibitive.
- **Columnar warehouse (ClickHouse/DuckDB-only)** — rejected as primary: Parquet+MinIO
  is frozen (§34.13), storage-class cheap, and interoperable with Qlib/Nautilus data
  tooling.
- **Cloud-specific blob (S3/GCS)** — rejected: MinIO keeps the platform self-hosted and
  the interface S3-compatible, allowing later migration.

## Consequences

- Positive: cheap, scalable, format-portable (Parquet works with Qlib/Pandas/Polars);
  medallion layers enforce data-quality staging.
- Negative: two data systems to operate — mitigated by the INV-10 responsibility split
  and by market-data owning temporal correctness.
- Follow-ups: Phase 1 delivers MinIO + catalog + normalization; data-quality gates reject
  stale/future data (Phase 1 DoD).

## Validation

- Frozen decision §34.13; §13 (medallion layout, contents); §27 (`data/catalogs`).
- INV-10 (stores separated by purpose).
- Repo evidence: no storage exists yet (PRE-00).
