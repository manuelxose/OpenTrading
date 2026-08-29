"""Integration tests: market data platform against the real local stack.

Requires ``make up`` (PostgreSQL + MinIO) and ``OT_INTEGRATION=1`` — otherwise
skipped, like the other integration suites. Verifies the full path with real
Parquet objects and the PostgreSQL catalog: ingest → seal → query → snapshot
with the absolute INV-3 filter.
"""

from __future__ import annotations

import os
from datetime import timedelta

import pytest
from adapters.market_data import (
    MarketDataPipeline,
    MarketDataRepository,
    MinioLayerStore,
    PostgresCatalog,
)
from adapters.market_data.hashing import snapshot_data_hash
from core.clock.clocks import VirtualClock
from core.domain.enums import Timeframe
from core.schemas.market_data import RawMarketRecord

from factories import FIXED_START

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("OT_INTEGRATION"),
        reason="local stack not running (make up)",
    ),
]

SOURCE = "integration-feed"


def _make_records(count: int) -> tuple[RawMarketRecord, ...]:
    records: list[RawMarketRecord] = []
    for index in range(count):
        event = FIXED_START + timedelta(minutes=index)
        records.append(
            RawMarketRecord(
                source=SOURCE,
                source_record_id=f"it-{index}",
                event_time=event,
                available_time=event,
                ingested_at=event,
                payload={
                    "symbol": "EUR/USD",
                    "timeframe": "1m",
                    "open": "1.08000",
                    "high": "1.08010",
                    "low": "1.07990",
                    "close": "1.08005",
                    "volume": "1000",
                },
            )
        )
    return tuple(records)


def _build() -> tuple[MarketDataPipeline, MarketDataRepository, VirtualClock]:
    from core.config.settings import get_settings

    settings = get_settings()
    store = MinioLayerStore(
        settings.minio_endpoint,
        settings.minio_access_key,
        settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    catalog = PostgresCatalog(settings.postgres_dsn)
    clock = VirtualClock(FIXED_START)
    pipeline = MarketDataPipeline(store, catalog, clock)
    return pipeline, MarketDataRepository(store, catalog), clock


def test_full_pipeline_roundtrip_with_real_stores() -> None:
    pipeline, repository, clock = _build()
    run = pipeline.ingest(SOURCE, _make_records(5), timeframe=Timeframe.M1)
    assert run.status.value == "SUCCEEDED"
    sealed = pipeline.seal("EURUSD", Timeframe.M1, version=1)
    assert len(sealed.dataset_hash) == 64

    as_of = FIXED_START + timedelta(minutes=2, seconds=30)
    bars = repository.bars(
        instrument_id="EURUSD", timeframe=Timeframe.M1, as_of=as_of, dataset_version=1
    )
    assert len(bars) == 3

    snapshot = repository.snapshot(
        instrument_id="EURUSD",
        timeframe=Timeframe.M1,
        as_of=as_of,
        dataset_version=1,
        clock=clock,
    )
    assert snapshot is not None
    assert snapshot.source_timestamp == FIXED_START + timedelta(minutes=2)

    # Reproducibility: a second pipeline over the same sealed version produces
    # the identical snapshot hash.
    _pipeline_b, repository_b, clock_b = _build()
    snapshot_b = repository_b.snapshot(
        instrument_id="EURUSD",
        timeframe=Timeframe.M1,
        as_of=as_of,
        dataset_version=1,
        clock=clock_b,
    )
    assert snapshot_b is not None
    assert snapshot_data_hash(snapshot) == snapshot_data_hash(snapshot_b)
