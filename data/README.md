# data/ — datasets, catalogs, fixtures (Phase 1, architecture §27)

Phase 1 is implemented. The medallion pipeline
(`adapters/market_data`, ADR-0011 + ADR-0017) stores heavy history in
MinIO/Parquet buckets `raw → bronze → silver → gold` and metadata/state in
PostgreSQL (`instruments`, `ingestion_runs`, `dataset_versions`,
`dataset_partitions`, `bar_gaps`; migration 0002). This directory keeps the
human-facing layout:

- `data/schemas/` — Parquet dataset schema conventions;
- `data/catalogs/` — dataset catalog conventions (gold manifests);
- `data/fixtures/` — deterministic test fixtures.

See `docs/architecture/PHASE1_DATA_PLATFORM.md`.
