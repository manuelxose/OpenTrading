"""Leakage tests: future information must be impossible to retrieve (INV-3).

Phase 1 Definition of Done:

1. ``(instrument X, dataset version Y, as_of T)`` always produces the exact
   same ``MarketSnapshot`` hash.
2. Future information is impossible to retrieve through the normal query API.

These tests deliberately insert future information into the store and prove
that the repository and the HTTP API reject it — the filter cannot be
bypassed, and sealed datasets are immutable.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from adapters.market_data.errors import DatasetSealedError, FutureDataLeakageError
from adapters.market_data.hashing import snapshot_data_hash
from apps.api.main import create_app
from core.clock.clocks import VirtualClock
from core.domain.enums import Timeframe
from fastapi.testclient import TestClient

from factories import FIXED_START
from market_data_platform import Platform, make_minute_raw_records


def _build_platform_with_poison() -> tuple[Platform, str]:
    """Six M1 bars at 10:00…10:05 plus deliberately planted future information:

    - a bar whose event_time is in-range (10:01) but whose available_time is
      tomorrow (late-published revision — must never appear for early as_of);
    - the platform sealing them as dataset version 1.
    """
    platform = Platform()
    records = make_minute_raw_records("feed-a", FIXED_START, count=6)
    poison = records[1].model_copy(
        update={
            "source_record_id": "poison-late-availability",
            "available_time": FIXED_START + timedelta(days=1),
        }
    )
    platform.pipeline.ingest("feed-a", (*records, poison), timeframe=Timeframe.M1)
    platform.pipeline.seal("EURUSD", Timeframe.M1, version=1)
    return platform, "poison-late-availability"


AS_OF_MID = FIXED_START + timedelta(minutes=2, seconds=30)


class TestRepositoryLeakage:
    def test_future_available_time_never_returned(self) -> None:
        platform, poison_id = _build_platform_with_poison()
        bars = platform.repository.bars(
            instrument_id="EURUSD", timeframe=Timeframe.M1, as_of=AS_OF_MID, dataset_version=1
        )
        returned_ids = {bar.source_record_id for bar in bars}
        assert poison_id not in returned_ids
        assert len(bars) == 3  # 10:00, 10:01, 10:02

    def test_snapshot_never_contains_future_info(self) -> None:
        platform, _ = _build_platform_with_poison()
        snapshot = platform.repository.snapshot(
            instrument_id="EURUSD",
            timeframe=Timeframe.M1,
            as_of=AS_OF_MID,
            dataset_version=1,
            clock=platform.clock,
        )
        assert snapshot is not None
        assert snapshot.source_timestamp == FIXED_START + timedelta(minutes=2)

    def test_every_visible_bar_satisfies_invariant(self) -> None:
        """Absolute invariant: no returned bar has available_time > as_of."""
        platform, _ = _build_platform_with_poison()
        for minutes in range(6):
            as_of = FIXED_START + timedelta(minutes=minutes, seconds=59)
            bars = platform.repository.bars(
                instrument_id="EURUSD", timeframe=Timeframe.M1, as_of=as_of, dataset_version=1
            )
            for bar in bars:
                assert bar.available_time <= as_of
                assert bar.event_time <= as_of

    def test_query_api_has_no_unfiltered_path(self) -> None:
        """bars/snapshot require as_of; there is no bypass method."""
        platform, _ = _build_platform_with_poison()
        with pytest.raises(TypeError):
            platform.repository.bars(  # type: ignore[call-arg]  # as_of missing
                instrument_id="EURUSD", timeframe=Timeframe.M1, dataset_version=1
            )


class TestApiLeakage:
    def test_http_api_rejects_future_information(self) -> None:
        platform, poison_id = _build_platform_with_poison()
        app = create_app(
            clock=platform.clock,
            market_data_repository=platform.repository,
            market_data_catalog=platform.catalog,
        )
        client = TestClient(app)
        response = client.get(
            "/api/v1/market-data/bars",
            params={
                "instrument_id": "EURUSD",
                "timeframe": "M1",
                "as_of": AS_OF_MID.isoformat(),
                "dataset_version": 1,
            },
        )
        assert response.status_code == 200
        bars = response.json()["bars"]
        assert poison_id not in {bar["source_record_id"] for bar in bars}
        assert len(bars) == 3

    def test_api_requires_explicit_as_of(self) -> None:
        platform, _ = _build_platform_with_poison()
        app = create_app(
            clock=platform.clock,
            market_data_repository=platform.repository,
            market_data_catalog=platform.catalog,
        )
        client = TestClient(app)
        response = client.get(
            "/api/v1/market-data/bars",
            params={"instrument_id": "EURUSD", "timeframe": "M1", "dataset_version": 1},
        )
        assert response.status_code == 422

    def test_api_requires_aware_timestamps(self) -> None:
        platform, _ = _build_platform_with_poison()
        app = create_app(
            clock=platform.clock,
            market_data_repository=platform.repository,
            market_data_catalog=platform.catalog,
        )
        client = TestClient(app)
        response = client.get(
            "/api/v1/market-data/bars",
            params={
                "instrument_id": "EURUSD",
                "timeframe": "M1",
                "as_of": "2026-01-05T10:02:30",  # naive → refused
                "dataset_version": 1,
            },
        )
        assert response.status_code == 422

    def test_api_snapshot_endpoint_has_no_future_info(self) -> None:
        platform, _ = _build_platform_with_poison()
        app = create_app(
            clock=platform.clock,
            market_data_repository=platform.repository,
            market_data_catalog=platform.catalog,
        )
        client = TestClient(app)
        response = client.get(
            "/api/v1/market-data/snapshots/EURUSD",
            params={
                "timeframe": "M1",
                "as_of": AS_OF_MID.isoformat(),
                "dataset_version": 1,
            },
        )
        assert response.status_code == 200
        body = response.json()
        # Pydantic v2 JSON mode serializes UTC as 'Z' (Phase 0 convention).
        from datetime import datetime as _dt

        source_timestamp = _dt.fromisoformat(
            body["snapshot"]["source_timestamp"].replace("Z", "+00:00")
        )
        assert source_timestamp == FIXED_START + timedelta(minutes=2)
        assert len(body["snapshot_hash"]) == 64


class TestDeterministicDoD:
    def test_same_dataset_and_as_of_gives_identical_snapshot_hash(self) -> None:
        """DoD: (instrument X, dataset version Y, as_of T) → same hash, always."""
        records = make_minute_raw_records("feed-a", FIXED_START, count=6)
        hashes: list[str] = []
        snapshots: list[dict[str, object]] = []
        for _ in range(3):  # three independent platform instances
            platform = Platform()
            platform.pipeline.ingest("feed-a", records, timeframe=Timeframe.M1)
            platform.pipeline.seal("EURUSD", Timeframe.M1, version=1)
            snapshot = platform.repository.snapshot(
                instrument_id="EURUSD",
                timeframe=Timeframe.M1,
                as_of=AS_OF_MID,
                dataset_version=1,
                clock=platform.clock,
            )
            assert snapshot is not None
            hashes.append(snapshot_data_hash(snapshot))
            snapshots.append(snapshot.canonical_dict())
        assert hashes[0] == hashes[1] == hashes[2]
        assert snapshots[0] == snapshots[1] == snapshots[2]

    def test_dataset_hashes_identical_across_rebuilds(self) -> None:
        records = make_minute_raw_records("feed-a", FIXED_START, count=6)
        platform_a, platform_b = Platform(), Platform()
        for platform in (platform_a, platform_b):
            platform.pipeline.ingest("feed-a", records, timeframe=Timeframe.M1)
        sealed_a = platform_a.pipeline.seal("EURUSD", Timeframe.M1, version=1)
        sealed_b = platform_b.pipeline.seal("EURUSD", Timeframe.M1, version=1)
        assert sealed_a.dataset_hash == sealed_b.dataset_hash

    def test_different_as_of_gives_different_snapshot_hash(self) -> None:
        platform = Platform()
        platform.pipeline.ingest(
            "feed-a",
            make_minute_raw_records("feed-a", FIXED_START, count=6),
            timeframe=Timeframe.M1,
        )
        platform.pipeline.seal("EURUSD", Timeframe.M1, version=1)
        early = platform.repository.snapshot(
            instrument_id="EURUSD",
            timeframe=Timeframe.M1,
            as_of=FIXED_START + timedelta(minutes=1),
            dataset_version=1,
            clock=platform.clock,
        )
        late = platform.repository.snapshot(
            instrument_id="EURUSD",
            timeframe=Timeframe.M1,
            as_of=AS_OF_MID,
            dataset_version=1,
            clock=platform.clock,
        )
        assert early is not None and late is not None
        assert snapshot_data_hash(early) != snapshot_data_hash(late)


class TestImmutabilityLeakage:
    def test_appending_to_sealed_version_impossible(self) -> None:
        platform = Platform()
        platform.pipeline.ingest(
            "feed-a",
            make_minute_raw_records("feed-a", FIXED_START, count=3),
            timeframe=Timeframe.M1,
        )
        platform.pipeline.seal("EURUSD", Timeframe.M1, version=1)
        with pytest.raises(DatasetSealedError):
            platform.catalog.seal_dataset(
                "ohlcv.EURUSD.M1",
                1,
                dataset_hash="f" * 64,
                row_count=9,
                event_min=FIXED_START,
                event_max=FIXED_START,
                avail_max=FIXED_START,
                sealed_at=FIXED_START,
                partitions=(),
            )

    def test_snapshot_guard_raises_on_direct_future_bar(self) -> None:
        from adapters.market_data.snapshot import snapshot_from_bar

        from factories import make_bar

        future_bar = make_bar(
            FIXED_START,
            source_record_id="future",
            available_time=FIXED_START + timedelta(hours=2),
        )
        with pytest.raises(FutureDataLeakageError):
            snapshot_from_bar(
                future_bar,
                as_of=FIXED_START,
                clock=VirtualClock(FIXED_START),
                dataset_id="ohlcv.EURUSD.M1",
                dataset_version=1,
            )
