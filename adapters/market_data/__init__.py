"""Market data adapter — Phase 1, normalization + point-in-time snapshots (INV-3).

Medallion pipeline ``RAW → BRONZE → SILVER → GOLD → MarketSnapshot``:

- :mod:`adapters.market_data.pipeline` — ingestion and gold sealing;
- :mod:`adapters.market_data.repository` — the only query path
  (:class:`~adapters.market_data.repository.PointInTimeFilter` is the single
  INV-3 choke point: no record with ``available_time > as_of`` can surface);
- :mod:`adapters.market_data.storage` — MinIO + Parquet (ADR-0011) with an
  in-memory twin for deterministic tests;
- :mod:`adapters.market_data.catalog` — PostgreSQL metadata/state (ADR-0010);
- :mod:`adapters.market_data.hashing` — deterministic dataset/snapshot hashes.
"""

from adapters.market_data.catalog import Catalog, MemoryCatalog, PostgresCatalog
from adapters.market_data.pipeline import MarketDataPipeline
from adapters.market_data.repository import MarketDataRepository, PointInTimeFilter
from adapters.market_data.snapshot import snapshot_from_bar
from adapters.market_data.storage import MemoryLayerStore, MinioLayerStore

__all__ = [
    "Catalog",
    "MarketDataPipeline",
    "MarketDataRepository",
    "MemoryCatalog",
    "MemoryLayerStore",
    "MinioLayerStore",
    "PointInTimeFilter",
    "PostgresCatalog",
    "snapshot_from_bar",
]
