# data/catalogs — dataset catalogs (Phase 1)

Implemented: PostgreSQL catalog tables (`dataset_versions`,
`dataset_partitions`, `ingestion_runs`, `instruments`, `bar_gaps`) with the
in-memory twin for tests (`adapters/market_data/catalog.py`). Gold versions are
immutable once sealed and carry a deterministic `dataset_hash`; every read
verifies partition checksums against the gold `_manifest.json`.

