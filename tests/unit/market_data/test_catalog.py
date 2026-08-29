"""Unit tests: catalog state semantics (memory implementation)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from adapters.market_data.catalog import MemoryCatalog
from adapters.market_data.errors import (
    DatasetNotFoundError,
    DatasetSealedError,
    DatasetVersionExistsError,
)
from core.domain.enums import DatasetState, IngestionStatus, MarketDataClass, Timeframe

from factories import FIXED_START, make_instrument


def test_instrument_upsert_keeps_first() -> None:
    catalog = MemoryCatalog()
    instrument = make_instrument(FIXED_START)
    catalog.ensure_instrument(instrument, "test", FIXED_START)
    other = instrument.model_copy(update={"exchange": "OTHER"})
    catalog.ensure_instrument(other, "test", FIXED_START)
    assert catalog.get_instrument("EURUSD").exchange == "FX"  # type: ignore[union-attr]
    assert len(catalog.list_instruments()) == 1


def test_run_lifecycle() -> None:
    catalog = MemoryCatalog()
    run_id = catalog.start_run("feed", MarketDataClass.OHLCV, FIXED_START)
    catalog.finish_run(run_id, IngestionStatus.SUCCEEDED, {"raw": 3}, FIXED_START)
    # Memory catalog keeps runs private; public behavior: no error and gaps ok.
    catalog.register_gaps(run_id, ())


def test_open_seal_get_roundtrip() -> None:
    catalog = MemoryCatalog()
    opened = catalog.open_dataset(
        "ohlcv.EURUSD.M1",
        "EURUSD",
        MarketDataClass.OHLCV,
        Timeframe.M1,
        version=1,
        opened_at=FIXED_START,
    )
    assert opened.state is DatasetState.OPEN
    sealed = catalog.seal_dataset(
        "ohlcv.EURUSD.M1",
        1,
        dataset_hash="abc",
        row_count=1,
        event_min=FIXED_START,
        event_max=FIXED_START,
        avail_max=FIXED_START,
        sealed_at=FIXED_START + timedelta(seconds=1),
        partitions=(),
    )
    assert sealed.state is DatasetState.SEALED
    assert sealed.dataset_hash == "abc"
    assert catalog.get_dataset("ohlcv.EURUSD.M1", 1) == sealed
    assert catalog.latest_sealed("ohlcv.EURUSD.M1") == sealed


def test_double_open_rejected() -> None:
    catalog = MemoryCatalog()
    catalog.open_dataset("d", "EURUSD", MarketDataClass.OHLCV, Timeframe.M1, 1, FIXED_START)
    with pytest.raises(DatasetVersionExistsError):
        catalog.open_dataset("d", "EURUSD", MarketDataClass.OHLCV, Timeframe.M1, 1, FIXED_START)


def test_double_seal_rejected_immutability() -> None:
    catalog = MemoryCatalog()
    catalog.open_dataset("d", "EURUSD", MarketDataClass.OHLCV, Timeframe.M1, 1, FIXED_START)
    catalog.seal_dataset(
        "d",
        1,
        dataset_hash="abc",
        row_count=1,
        event_min=FIXED_START,
        event_max=FIXED_START,
        avail_max=FIXED_START,
        sealed_at=FIXED_START,
        partitions=(),
    )
    with pytest.raises(DatasetSealedError):
        catalog.seal_dataset(
            "d",
            1,
            dataset_hash="xyz",
            row_count=1,
            event_min=FIXED_START,
            event_max=FIXED_START,
            avail_max=FIXED_START,
            sealed_at=FIXED_START,
            partitions=(),
        )


def test_seal_unknown_dataset_rejected() -> None:
    catalog = MemoryCatalog()
    with pytest.raises(DatasetNotFoundError):
        catalog.seal_dataset(
            "nope",
            1,
            dataset_hash="abc",
            row_count=1,
            event_min=FIXED_START,
            event_max=FIXED_START,
            avail_max=FIXED_START,
            sealed_at=FIXED_START,
            partitions=(),
        )


def test_latest_sealed_picks_highest_version() -> None:
    catalog = MemoryCatalog()
    for version in (1, 2):
        catalog.open_dataset(
            "d", "EURUSD", MarketDataClass.OHLCV, Timeframe.M1, version, FIXED_START
        )
        catalog.seal_dataset(
            "d",
            version,
            dataset_hash="abc",
            row_count=1,
            event_min=FIXED_START,
            event_max=FIXED_START,
            avail_max=FIXED_START,
            sealed_at=FIXED_START,
            partitions=(),
        )
    catalog.open_dataset("d", "EURUSD", MarketDataClass.OHLCV, Timeframe.M1, 3, FIXED_START)
    assert catalog.latest_sealed("d").version == 2  # type: ignore[union-attr]
