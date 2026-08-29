# Phase 1 — Data Platform: Market Data Implementation Record

- **Date:** 2026-08-26
- **Scope:** Milestone 2 / Phase 1 from `IMPLEMENTATION_ORDER.md` — the market
  data half of the Data Platform: medallion pipeline, point-in-time semantics,
  MinIO + Parquet storage, PostgreSQL catalog, and the leak-proof query layer.
  (Local infrastructure services were delivered in the previous milestone; see
  `docs/runbooks/infrastructure.md`.)
- **Canonical sources:** `docs/architecture.md` §12, §13, §27; ADR-0010
  (PostgreSQL truth), ADR-0011 (MinIO/Parquet), ADR-0017 (PIT semantics);
  invariants INV-3, INV-10.

## 1. What was built

### Pipeline: RAW → BRONZE → SILVER → GOLD → MarketSnapshot

| Layer | Location | Contents |
|---|---|---|
| RAW | MinIO `raw/{source}/{data_class}/runs/{run_id}/records.parquet` | Verbatim source payloads + ingestion envelope |
| BRONZE | MinIO `bronze/{data_class}/{instrument}/{timeframe}/run={run_id}/…` | Normalized bars: instrument + timezone normalization, `available_time` resolved |
| SILVER | MinIO `silver/…/run={run_id}/…` | Deduplicated, quality-flagged bars; gap records → PostgreSQL `bar_gaps` |
| GOLD | MinIO `gold/{data_class}/{instrument}/{timeframe}/v{version}/year=…/month=…/part-*.parquet` + `_manifest.json` | Immutable, hash-sealed dataset versions |
| MarketSnapshot | derived on demand | `adapters.market_data.repository.MarketDataRepository.snapshot()` |

- `adapters/market_data/pipeline.py` — `MarketDataPipeline.ingest()` (one run =
  one `MarketDataClass`) and `.seal()` (deterministic gold version).
- `adapters/market_data/normalization.py` — `SymbolNormalizer`
  (registry → normalized-form → derived uppercase), `normalize_timestamp`
  (aware/naive/ISO/epoch → UTC; declared timezone honored, UTC otherwise),
  deterministic OHLCV payload mapping with a fixed alias table.
- `adapters/market_data/quality.py` — flags (`OK`, `DUPLICATE`, `STALE`,
  `FUTURE_DATED`, `PRICE_ANOMALY`, `AVAILABLE_TIME_INFERRED`), deterministic
  duplicate resolution, interior missing-bar detection (calendar-aware D1/W1/MN1
  grids).
- `adapters/market_data/hashing.py` — canonical row bytes, per-row checksums,
  partition/dataset SHA-256, `snapshot_data_hash` (data fields only).
- `adapters/market_data/storage.py` — `LayerStore` protocol, `MemoryLayerStore`
  (tests), `MinioLayerStore` + Parquet codecs (decimal128(38,8), tz-aware
  microsecond timestamps).
- `adapters/market_data/catalog.py` + `catalog_db.py` — `MemoryCatalog`,
  `PostgresCatalog` over tables `instruments`, `ingestion_runs`,
  `dataset_versions`, `dataset_partitions`, `bar_gaps` (migration `0002`).

### Point-in-time query layer

- `adapters/market_data/repository.py` — `PointInTimeFilter` is the **single
  choke point** enforcing the absolute invariant: no record with
  `available_time > as_of` (nor `event_time > as_of`) is ever returned.
- `MarketDataRepository.bars()` / `.snapshot()` require explicit `as_of` and
  `dataset_version`; loading re-verifies partition checksums and the dataset
  hash against the manifest (tamper detection), and a defense-in-depth guard
  raises `FutureDataLeakageError` if any posterior row ever reaches the query
  surface.
- `adapters/market_data/snapshot.py` — `snapshot_from_bar()` with the
  documented zero-spread OHLCV assumption (`bid = ask = close`).

### HTTP API (`apps/api/market_data.py`)

- `GET /api/v1/market-data/instruments`
- `GET /api/v1/market-data/bars` — `as_of` and `dataset_version` **required**
- `GET /api/v1/market-data/snapshots/{instrument_id}` — returns the snapshot
  plus its deterministic `snapshot_hash`
- Missing dataset → 404, OPEN dataset → 409, naive timestamps → 422.

### Extensibility for fundamentals / macro / news

New data domains add payload mappers per `MarketDataClass` and reuse the same
layers, storage, catalog and filter — no redesign (ADR-0017).

## 2. Definition of Done — evidence

| Criterion | Status | Evidence |
|---|---|---|
| `(instrument X, dataset version Y, as_of T)` → identical `MarketSnapshot` hash | ✅ | `tests/leakage/test_point_in_time_leakage.py::TestDeterministicDoD` — three independent platform instances produce byte-identical snapshots and hashes |
| Future information impossible via the normal query API | ✅ | Same suite: deliberately planted future `available_time` bars are excluded by repository and HTTP API; `as_of`/`dataset_version` mandatory; naive timestamps rejected |
| Sealed datasets immutable | ✅ | Re-seal and gold-tamper attempts raise `DatasetSealedError` (checksum/hash verification on every read) |
| Instrument + timezone normalization | ✅ | `tests/unit/market_data/test_normalization.py` |
| Duplicate / missing-bar / stale / quality flags | ✅ | `tests/unit/market_data/test_quality.py`, `test_pipeline.py` |
| Parquet/MinIO for history, PostgreSQL for catalog/state | ✅ | `MinioLayerStore` + Parquet codecs (`test_storage.py`); migration `0002`; `tests/integration/test_market_data_integration.py` (real stack, `OT_INTEGRATION`) |
| Stale data rejected/flagged | ✅ | `STALE` flag per `OT_MARKET_DATA_STALE_AFTER_SECONDS` (default 3600) |

## 3. Checks run

- `uv run pytest`: 301 passed, 6 skipped (integration requires the local stack
  on this box; verified against real MinIO/PostgreSQL via
  `tests/integration/test_market_data_integration.py` with `make test-integration`).
- `uv run ruff check .` and `ruff format --check` — clean.
- `uv run mypy core apps engines adapters` (strict) — clean.
- `uv run alembic upgrade head` applies `0001` + `0002` (runtime DoD on a Docker
  host).

## 4. Operational notes

- Re-ingesting after sealing does not mutate gold — it creates a new version
  (`seal(..., version=N+1)`); `latest_sealed()` resolves the current one.
- The gold manifest (`_manifest.json`) is redundant with the PostgreSQL catalog
  on purpose: reads verify both, so silent object tampering is impossible.
- OHLCV snapshots assume zero spread (`bid = ask = close`); a spread model is a
  Phase 4 (Nautilus) concern and will plug into snapshot derivation, not into
  the dataset layers.
