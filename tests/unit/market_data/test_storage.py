"""Unit tests: layer storage (memory store + Parquet codecs)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from adapters.market_data.storage import (
    MemoryLayerStore,
    bars_to_parquet,
    gold_part_key,
    manifest_key,
    parquet_to_bars,
    parquet_to_raw,
    raw_to_parquet,
    run_bars_key,
)
from core.domain.enums import DataQualityFlag, LayerName, Timeframe

from factories import FIXED_START, make_bar, make_raw_market_record


class TestMemoryStore:
    def test_roundtrip_bars_and_json(self) -> None:
        store = MemoryLayerStore()
        bars = (make_bar(FIXED_START), make_bar(FIXED_START + timedelta(minutes=1)))
        store.write_bars(LayerName.SILVER, "k", bars)
        assert store.read_bars(LayerName.SILVER, "k") == bars
        store.write_json(LayerName.GOLD, "m", {"hash": "abc"})
        assert store.read_json(LayerName.GOLD, "m") == {"hash": "abc"}
        assert store.list_keys(LayerName.SILVER, "") == ["k"]

    def test_list_keys_filters_prefix(self) -> None:
        store = MemoryLayerStore()
        store.write_json(LayerName.GOLD, "a/1", {})
        store.write_json(LayerName.GOLD, "a/2", {})
        store.write_json(LayerName.GOLD, "b/1", {})
        assert store.list_keys(LayerName.GOLD, "a/") == ["a/1", "a/2"]


class TestParquetCodecs:
    def test_bars_roundtrip(self) -> None:
        bars = (
            make_bar(FIXED_START, quality_flags=(DataQualityFlag.OK,), checksum="c0"),
            make_bar(
                FIXED_START + timedelta(minutes=1),
                source_record_id="x",
                volume="0",
                checksum=None,
            ),
        )
        restored = parquet_to_bars(bars_to_parquet(bars))
        assert restored == bars

    def test_decimal_precision_beyond_8dp_quantized(self) -> None:
        bar = make_bar(FIXED_START, close="1.080051234")
        restored = parquet_to_bars(bars_to_parquet((bar,)))[0]
        assert restored.close == Decimal("1.08005123")  # ROUND_HALF_EVEN to 8 dp

    def test_raw_roundtrip_with_null_available_time(self) -> None:
        records = (
            make_raw_market_record(FIXED_START),
            make_raw_market_record(FIXED_START + timedelta(minutes=1), available_time=None),
        )
        restored = parquet_to_raw(raw_to_parquet(records))
        assert restored == records

    def test_empty_payload_parses(self) -> None:
        assert parquet_to_bars(b"") == ()
        assert parquet_to_raw(b"") == ()


class TestKeyLayout:
    def test_gold_part_key_deterministic(self) -> None:
        from core.domain.enums import MarketDataClass

        key = gold_part_key(
            MarketDataClass.OHLCV, "EURUSD", Timeframe.M1, version=7, year=2026, month=1, index=0
        )
        assert key == "OHLCV/EURUSD/M1/v000007/year=2026/month=01/part-00000.parquet"

    def test_run_bars_key(self) -> None:
        from core.domain.enums import MarketDataClass

        key = run_bars_key(MarketDataClass.OHLCV, "EURUSD", Timeframe.H1, "run-1")
        assert key == "OHLCV/EURUSD/H1/run=run-1/part-00000.parquet"

    def test_manifest_key(self) -> None:
        from core.domain.enums import MarketDataClass

        assert manifest_key(MarketDataClass.OHLCV, "EURUSD", Timeframe.H1, 3) == (
            "OHLCV/EURUSD/H1/v000003/_manifest.json"
        )
