"""Dataset determinism: synthetic generation, spread synthesis, parquet replay."""

from __future__ import annotations

import pyarrow as pa
import pyarrow.parquet as pq
from adapters.nautilus.config import DatasetConfig, SpreadConfig
from adapters.nautilus.dataset import build_dataset, synthetic_dataset
from nautilus_trader.model.identifiers import Venue
from parquet_helpers import write_bars_parquet

from factories import FIXED_START, make_instrument


def _build(seed: int = 7, n_bars: int = 50, half_spread_ticks: int = 1):
    config = DatasetConfig(seed=seed, n_bars=n_bars)
    instrument = make_instrument(FIXED_START)
    spread = SpreadConfig(half_spread_ticks=half_spread_ticks)
    return config, instrument, spread


def test_synthetic_dataset_is_reproducible() -> None:
    config, instrument, spread = _build()
    venue = Venue("SIM")
    d1 = synthetic_dataset(config, instrument, spread, venue)
    d2 = synthetic_dataset(config, instrument, spread, venue)
    assert d1.dataset_hash == d2.dataset_hash
    assert [b.close for b in d1.bars] == [b.close for b in d2.bars]


def test_different_seed_gives_different_dataset() -> None:
    config_a, instrument, spread = _build(seed=7)
    config_b, _, _ = _build(seed=8)
    venue = Venue("SIM")
    assert (
        synthetic_dataset(config_a, instrument, spread, venue).dataset_hash
        != synthetic_dataset(config_b, instrument, spread, venue).dataset_hash
    )


def test_bars_and_quotes_share_timestamps_and_count() -> None:
    config, instrument, spread = _build()
    dataset = synthetic_dataset(config, instrument, spread, Venue("SIM"))
    assert len(dataset.bars) == len(dataset.quotes) == config.n_bars
    assert [b.ts_event for b in dataset.bars] == [q.ts_event for q in dataset.quotes]


def test_spread_is_applied_to_quotes() -> None:
    config, instrument, spread = _build(half_spread_ticks=2)
    tick = instrument.tick_size
    dataset = synthetic_dataset(config, instrument, spread, Venue("SIM"))
    for bar, quote in zip(dataset.bars, dataset.quotes, strict=True):
        mid = bar.close.as_decimal()
        assert quote.ask_price.as_decimal() - quote.bid_price.as_decimal() == 4 * tick
        assert quote.bid_price.as_decimal() <= mid <= quote.ask_price.as_decimal()


def test_parquet_replay_matches_synthetic_hash(tmp_path) -> None:
    config, instrument, spread = _build()
    venue = Venue("SIM")
    dataset = synthetic_dataset(config, instrument, spread, venue)

    path = tmp_path / "eurusd.parquet"
    write_bars_parquet(dataset, path)

    replayed = build_dataset(
        DatasetConfig(source="parquet", path=path, seed=config.seed),
        instrument,
        spread,
        venue,
    )
    assert replayed.dataset_hash == dataset.dataset_hash


def test_bar_prices_respect_tick_and_ohlc_shape() -> None:
    config, instrument, spread = _build()
    tick = instrument.tick_size
    dataset = synthetic_dataset(config, instrument, spread, Venue("SIM"))
    for bar in dataset.bars:
        o, h, lo, c = (
            bar.open.as_decimal(),
            bar.high.as_decimal(),
            bar.low.as_decimal(),
            bar.close.as_decimal(),
        )
        assert h >= max(o, c)
        assert lo <= min(o, c)
        for price in (o, h, lo, c):
            assert price / tick == (price / tick).to_integral_value()


def test_parquet_loader_rejects_duplicate_ts(tmp_path) -> None:
    config, instrument, spread = _build()
    venue = Venue("SIM")
    dataset = synthetic_dataset(config, instrument, spread, venue)
    rows = [
        {
            "ts_event": bar.ts_event,
            "open": float(bar.open.as_decimal()),
            "high": float(bar.high.as_decimal()),
            "low": float(bar.low.as_decimal()),
            "close": float(bar.close.as_decimal()),
            "volume": int(bar.volume.as_decimal()),
        }
        for bar in dataset.bars
    ]
    rows.append(rows[-1])  # duplicate last timestamp
    path = tmp_path / "dup.parquet"
    pq.write_table(pa.Table.from_pylist(rows), path)
    import pytest

    with pytest.raises(ValueError, match="duplicate"):
        build_dataset(DatasetConfig(source="parquet", path=path), instrument, spread, venue)
