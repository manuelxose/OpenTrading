"""Unit tests: point-in-time query layer and snapshot generation."""

from __future__ import annotations

from datetime import timedelta

import pytest
from adapters.market_data.errors import (
    DatasetNotFoundError,
    DatasetNotSealedError,
    DatasetSealedError,
    FutureDataLeakageError,
)
from adapters.market_data.repository import PointInTimeFilter
from adapters.market_data.snapshot import snapshot_from_bar
from core.domain.enums import LayerName, MarketDataClass, Timeframe
from core.schemas.market import MarketSnapshot

from factories import FIXED_START, make_bar
from market_data_platform import Platform, make_minute_raw_records


class TestPointInTimeFilter:
    def test_drops_available_time_after_as_of(self) -> None:
        bars = (
            make_bar(FIXED_START, source_record_id="ok"),
            make_bar(
                FIXED_START + timedelta(minutes=1),
                source_record_id="late",
                available_time=FIXED_START + timedelta(hours=1),
            ),
        )
        result = PointInTimeFilter(FIXED_START + timedelta(minutes=30)).apply(bars)
        assert [bar.source_record_id for bar in result] == ["ok"]

    def test_drops_event_time_after_as_of(self) -> None:
        bars = (
            make_bar(FIXED_START, source_record_id="ok"),
            make_bar(FIXED_START + timedelta(minutes=1), source_record_id="future"),
        )
        result = PointInTimeFilter(FIXED_START + timedelta(seconds=30)).apply(bars)
        assert [bar.source_record_id for bar in result] == ["ok"]

    def test_boundary_is_inclusive(self) -> None:
        bars = (make_bar(FIXED_START, source_record_id="edge"),)
        assert len(PointInTimeFilter(FIXED_START).apply(bars)) == 1


def _sealed_platform(records, **kwargs: object) -> Platform:
    platform = Platform()
    platform.pipeline.ingest("feed-a", records, timeframe=Timeframe.M1)
    platform.pipeline.seal("EURUSD", Timeframe.M1, version=1)
    return platform


class TestRepository:
    def test_bars_applies_as_of_filter_and_range(self) -> None:
        platform = _sealed_platform(make_minute_raw_records("feed-a", FIXED_START, count=6))
        repo = platform.repository
        as_of = FIXED_START + timedelta(minutes=2, seconds=30)
        bars = repo.bars(
            instrument_id="EURUSD",
            timeframe=Timeframe.M1,
            as_of=as_of,
            dataset_version=1,
        )
        assert len(bars) == 3  # 10:00, 10:01, 10:02
        ranged = repo.bars(
            instrument_id="EURUSD",
            timeframe=Timeframe.M1,
            as_of=as_of,
            dataset_version=1,
            start=FIXED_START + timedelta(minutes=1),
            end=FIXED_START + timedelta(minutes=2),
        )
        assert len(ranged) == 2

    def test_late_available_bar_invisible_even_when_event_in_range(self) -> None:
        records = make_minute_raw_records("feed-a", FIXED_START, count=3)
        poison = records[1].model_copy(
            update={
                "source_record_id": "poison",
                "available_time": FIXED_START + timedelta(days=1),  # future availability
            }
        )
        platform = _sealed_platform((*records, poison))
        as_of = FIXED_START + timedelta(minutes=3)
        bars = platform.repository.bars(
            instrument_id="EURUSD", timeframe=Timeframe.M1, as_of=as_of, dataset_version=1
        )
        assert all(bar.source_record_id != "poison" for bar in bars)
        assert len(bars) == 3

    def test_snapshot_uses_latest_visible_bar(self) -> None:
        platform = _sealed_platform(make_minute_raw_records("feed-a", FIXED_START, count=4))
        snapshot = platform.repository.snapshot(
            instrument_id="EURUSD",
            timeframe=Timeframe.M1,
            as_of=FIXED_START + timedelta(minutes=2, seconds=30),
            dataset_version=1,
            clock=platform.clock,
        )
        assert isinstance(snapshot, MarketSnapshot)
        assert snapshot.source_timestamp == FIXED_START + timedelta(minutes=2)
        assert snapshot.bid == snapshot.ask == snapshot.close  # zero-spread assumption

    def test_snapshot_none_before_first_bar(self) -> None:
        platform = _sealed_platform(make_minute_raw_records("feed-a", FIXED_START, count=2))
        snapshot = platform.repository.snapshot(
            instrument_id="EURUSD",
            timeframe=Timeframe.M1,
            as_of=FIXED_START - timedelta(minutes=1),
            dataset_version=1,
            clock=platform.clock,
        )
        assert snapshot is None

    def test_missing_dataset_raises(self) -> None:
        platform = Platform()
        with pytest.raises(DatasetNotFoundError):
            platform.repository.bars(
                instrument_id="EURUSD",
                timeframe=Timeframe.M1,
                as_of=FIXED_START,
                dataset_version=9,
            )

    def test_open_dataset_not_readable(self) -> None:
        platform = Platform()
        platform.pipeline.ingest(
            "feed-a", make_minute_raw_records("feed-a", FIXED_START, 2), timeframe=Timeframe.M1
        )
        platform.catalog.open_dataset(
            "ohlcv.EURUSD.M1", "EURUSD", MarketDataClass.OHLCV, Timeframe.M1, 1, FIXED_START
        )
        with pytest.raises(DatasetNotSealedError):
            platform.repository.bars(
                instrument_id="EURUSD",
                timeframe=Timeframe.M1,
                as_of=FIXED_START,
                dataset_version=1,
            )

    def test_tampered_gold_object_detected(self) -> None:
        platform = _sealed_platform(make_minute_raw_records("feed-a", FIXED_START, count=2))
        # Tamper: overwrite a gold partition with different content.
        key = "OHLCV/EURUSD/M1/v000001/year=2026/month=01/part-00000.parquet"
        bars = platform.store.read_bars(LayerName.GOLD, key)
        tampered = tuple(bar.model_copy(update={"close": bar.close + 1}) for bar in bars)
        platform.store.write_bars(LayerName.GOLD, key, tampered)
        with pytest.raises(DatasetSealedError):
            platform.repository.bars(
                instrument_id="EURUSD",
                timeframe=Timeframe.M1,
                as_of=FIXED_START,
                dataset_version=1,
            )

    def test_manifest_swapped_detected(self) -> None:
        platform = _sealed_platform(make_minute_raw_records("feed-a", FIXED_START, count=2))
        manifest_key_path = "OHLCV/EURUSD/M1/v000001/_manifest.json"
        manifest = platform.store.read_json(LayerName.GOLD, manifest_key_path)
        manifest["dataset_hash"] = "0" * 64
        platform.store.write_json(LayerName.GOLD, manifest_key_path, manifest)
        with pytest.raises(DatasetSealedError):
            platform.repository.bars(
                instrument_id="EURUSD",
                timeframe=Timeframe.M1,
                as_of=FIXED_START,
                dataset_version=1,
            )


class TestSnapshotDerivationGuard:
    def test_future_bar_rejected_even_directly(self) -> None:
        bar = make_bar(FIXED_START, available_time=FIXED_START + timedelta(days=1))
        with pytest.raises(FutureDataLeakageError):
            snapshot_from_bar(
                bar,
                as_of=FIXED_START,
                clock=Platform().clock,
                dataset_id="ohlcv.EURUSD.M1",
                dataset_version=1,
            )

    def test_ok_bar_produces_snapshot(self) -> None:
        bar = make_bar(FIXED_START)
        snapshot = snapshot_from_bar(
            bar,
            as_of=FIXED_START,
            clock=Platform().clock,
            dataset_id="ohlcv.EURUSD.M1",
            dataset_version=1,
        )
        assert snapshot.as_of == FIXED_START
        assert snapshot.source_timestamp == bar.event_time
