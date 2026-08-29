"""Unit tests: market data HTTP API (in-memory doubles)."""

from __future__ import annotations

from datetime import timedelta

from apps.api.main import create_app
from core.domain.enums import MarketDataClass, Timeframe
from fastapi.testclient import TestClient

from factories import FIXED_START, make_instrument
from market_data_platform import Platform, make_minute_raw_records


def _client(platform: Platform) -> TestClient:
    app = create_app(
        clock=platform.clock,
        market_data_repository=platform.repository,
        market_data_catalog=platform.catalog,
    )
    return TestClient(app)


def test_instruments_listing() -> None:
    platform = Platform()
    platform.catalog.ensure_instrument(make_instrument(FIXED_START), "test", FIXED_START)
    response = _client(platform).get("/api/v1/market-data/instruments")
    assert response.status_code == 200
    body = response.json()
    assert body["instruments"][0]["instrument_id"] == "EURUSD"


def test_bars_endpoint_returns_filtered_bars() -> None:
    platform = Platform()
    platform.pipeline.ingest(
        "feed-a",
        make_minute_raw_records("feed-a", FIXED_START, count=4),
        timeframe=Timeframe.M1,
    )
    platform.pipeline.seal("EURUSD", Timeframe.M1, version=1)
    response = _client(platform).get(
        "/api/v1/market-data/bars",
        params={
            "instrument_id": "EURUSD",
            "timeframe": "M1",
            "as_of": (FIXED_START + timedelta(minutes=2)).isoformat(),
            "dataset_version": 1,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 3
    assert body["bars"][-1]["instrument_id"] == "EURUSD"


def test_unknown_dataset_404() -> None:
    platform = Platform()
    response = _client(platform).get(
        "/api/v1/market-data/bars",
        params={
            "instrument_id": "EURUSD",
            "timeframe": "M1",
            "as_of": FIXED_START.isoformat(),
            "dataset_version": 7,
        },
    )
    assert response.status_code == 404


def test_open_dataset_409() -> None:
    platform = Platform()
    platform.pipeline.ingest(
        "feed-a",
        make_minute_raw_records("feed-a", FIXED_START, count=2),
        timeframe=Timeframe.M1,
    )
    platform.catalog.open_dataset(
        "ohlcv.EURUSD.M1", "EURUSD", MarketDataClass.OHLCV, Timeframe.M1, 1, FIXED_START
    )
    response = _client(platform).get(
        "/api/v1/market-data/bars",
        params={
            "instrument_id": "EURUSD",
            "timeframe": "M1",
            "as_of": FIXED_START.isoformat(),
            "dataset_version": 1,
        },
    )
    assert response.status_code == 409


def test_snapshot_unknown_dataset_404() -> None:
    platform = Platform()
    response = _client(platform).get(
        "/api/v1/market-data/snapshots/EURUSD",
        params={
            "timeframe": "M1",
            "as_of": FIXED_START.isoformat(),
            "dataset_version": 7,
        },
    )
    assert response.status_code == 404


def test_snapshot_no_visible_bar_404() -> None:
    platform = Platform()
    platform.pipeline.ingest(
        "feed-a",
        make_minute_raw_records("feed-a", FIXED_START, count=2),
        timeframe=Timeframe.M1,
    )
    platform.pipeline.seal("EURUSD", Timeframe.M1, version=1)
    response = _client(platform).get(
        "/api/v1/market-data/snapshots/EURUSD",
        params={
            "timeframe": "M1",
            "as_of": (FIXED_START - timedelta(hours=1)).isoformat(),
            "dataset_version": 1,
        },
    )
    assert response.status_code == 404
