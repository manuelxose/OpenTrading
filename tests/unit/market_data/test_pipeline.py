"""Unit tests: medallion pipeline raw→bronze→silver→gold."""

from __future__ import annotations

from datetime import timedelta

import pytest
from adapters.market_data.errors import MarketDataError
from adapters.market_data.hashing import dataset_hash
from core.domain.enums import (
    DataQualityFlag,
    IngestionStatus,
    LayerName,
    MarketDataClass,
    Timeframe,
)

from factories import FIXED_START
from market_data_platform import Platform, make_minute_raw_records


def test_ingest_writes_all_layers_and_stats() -> None:
    # Clock 10 minutes after the first event so available_times are not future
    # relative to the ingest clock (FUTURE_DATED is a clock-relative flag).
    platform = Platform(start=FIXED_START + timedelta(minutes=10))
    records = make_minute_raw_records("feed-a", FIXED_START, count=3)
    run = platform.pipeline.ingest("feed-a", records, timeframe=Timeframe.M1)
    assert run.status is IngestionStatus.SUCCEEDED
    assert run.stats == {
        "raw_records": 3,
        "bronze_bars": 3,
        "silver_bars": 3,
        "duplicates": 0,
        "gaps": 0,
        "stale": 0,
        "anomalies": 0,
        "future_dated": 0,
    }
    assert platform.store.list_keys(LayerName.RAW, "feed-a/") != []
    assert platform.store.list_keys(LayerName.BRONZE, "OHLCV/EURUSD/M1/") != []
    assert platform.store.list_keys(LayerName.SILVER, "OHLCV/EURUSD/M1/") != []


def test_ingest_normalizes_symbol_and_timezone() -> None:
    platform = Platform()
    records = make_minute_raw_records("feed-a", FIXED_START, count=1, symbol="eur/usd")
    platform.pipeline.ingest("feed-a", records, timeframe=Timeframe.M1)
    (bar,) = platform.store.read_bars(
        LayerName.BRONZE, platform.store.list_keys(LayerName.BRONZE, "OHLCV/EURUSD/M1/")[0]
    )
    assert bar.instrument_id == "EURUSD"
    assert bar.event_time.tzinfo is not None


def test_ingest_infers_available_time_and_flags_it() -> None:
    platform = Platform()
    record = make_minute_raw_records("feed-a", FIXED_START, count=1)[0].model_copy(
        update={"available_time": None}
    )
    platform.pipeline.ingest("feed-a", (record,), timeframe=Timeframe.M1)
    (bar,) = platform.store.read_bars(
        LayerName.SILVER, platform.store.list_keys(LayerName.SILVER, "OHLCV/EURUSD/M1/")[0]
    )
    assert DataQualityFlag.AVAILABLE_TIME_INFERRED in bar.quality_flags
    assert bar.available_time == platform.clock.now()


def test_ingest_detects_missing_bars() -> None:
    platform = Platform()
    records = make_minute_raw_records("feed-a", FIXED_START, count=1)
    later = records[0].model_copy(
        update={"source_record_id": "later", "event_time": FIXED_START + timedelta(minutes=4)}
    )
    run = platform.pipeline.ingest("feed-a", (records[0], later), timeframe=Timeframe.M1)
    assert run.stats["gaps"] == 3
    assert len(run.gaps) == 3


def test_ingest_rejects_mixed_data_classes() -> None:
    platform = Platform()
    records = make_minute_raw_records("feed-a", FIXED_START, count=1)
    macro = records[0].model_copy(update={"data_class": MarketDataClass.MACRO})
    with pytest.raises(MarketDataError):
        platform.pipeline.ingest("feed-a", (records[0], macro), timeframe=Timeframe.M1)


def test_seal_produces_deterministic_hash_across_platforms() -> None:
    records = make_minute_raw_records("feed-a", FIXED_START, count=6)
    platform_a = Platform()
    platform_b = Platform()
    platform_a.pipeline.ingest("feed-a", records, timeframe=Timeframe.M1)
    platform_b.pipeline.ingest("feed-a", records, timeframe=Timeframe.M1)
    sealed_a = platform_a.pipeline.seal("EURUSD", Timeframe.M1, version=1)
    sealed_b = platform_b.pipeline.seal("EURUSD", Timeframe.M1, version=1)
    assert sealed_a.dataset_hash == sealed_b.dataset_hash
    assert sealed_a.row_count == sealed_b.row_count == 6
    assert len(sealed_a.partitions) == len(sealed_b.partitions) == 1


def test_seal_excludes_duplicates_from_gold() -> None:
    platform = Platform()
    records = make_minute_raw_records("feed-a", FIXED_START, count=2)
    dup = records[0].model_copy(update={"source_record_id": records[0].source_record_id})
    platform.pipeline.ingest("feed-a", (*records, dup), timeframe=Timeframe.M1)
    sealed = platform.pipeline.seal("EURUSD", Timeframe.M1, version=1)
    assert sealed.row_count == 2


def test_seal_without_data_raises() -> None:
    platform = Platform()
    with pytest.raises(MarketDataError):
        platform.pipeline.seal("EURUSD", Timeframe.M1, version=1)


def test_second_version_gets_distinct_hash_and_content() -> None:
    platform = Platform()
    platform.pipeline.ingest(
        "feed-a", make_minute_raw_records("feed-a", FIXED_START, count=2), timeframe=Timeframe.M1
    )
    v1 = platform.pipeline.seal("EURUSD", Timeframe.M1, version=1)
    platform.pipeline.ingest(
        "feed-a", make_minute_raw_records("feed-a", FIXED_START, count=5), timeframe=Timeframe.M1
    )
    v2 = platform.pipeline.seal("EURUSD", Timeframe.M1, version=2)
    assert v1.dataset_hash != v2.dataset_hash
    assert v2.row_count == 5


def test_gold_manifest_hash_matches_catalog() -> None:
    platform = Platform()
    platform.pipeline.ingest(
        "feed-a", make_minute_raw_records("feed-a", FIXED_START, count=3), timeframe=Timeframe.M1
    )
    platform.pipeline.seal("EURUSD", Timeframe.M1, version=1)
    manifest = platform.store.read_json(LayerName.GOLD, "OHLCV/EURUSD/M1/v000001/_manifest.json")
    assert manifest["dataset_hash"] == dataset_hash(
        platform.store.read_bars(
            LayerName.GOLD, "OHLCV/EURUSD/M1/v000001/year=2026/month=01/part-00000.parquet"
        )
    )
