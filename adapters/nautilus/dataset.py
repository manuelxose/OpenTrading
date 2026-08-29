"""Deterministic historical datasets for Nautilus replay (ADR-0007).

Two sources are supported:

- ``synthetic``: a seeded geometric-Brownian-motion OHLCV series — byte-for-byte
  reproducible from ``DatasetConfig`` alone (used by the DoD tests);
- ``parquet``: a real historical OHLCV file replayed through the same code path.

``Dataset.dataset_hash`` covers the *normalized* rows (sorted, canonical strings),
so the same history loaded from synthetic generation or from a parquet file yields
the same hash.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from math import exp, sqrt
from pathlib import Path

from core.schemas import Instrument
from nautilus_trader.core.datetime import dt_to_unix_nanos, unix_nanos_to_dt
from nautilus_trader.model.data import Bar, BarSpecification, BarType, QuoteTick
from nautilus_trader.model.enums import BarAggregation, PriceType
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.objects import Price, Quantity

from adapters.nautilus.config import DatasetConfig, SpreadConfig

__all__ = ["Dataset", "build_dataset", "load_parquet_dataset", "synthetic_dataset"]

_QUOTE_SIZE = 1_000_000


@dataclass(frozen=True)
class Dataset:
    """Bars + synthesized quotes for one instrument, plus a canonical row hash."""

    instrument_id: str
    bars: list[Bar]
    quotes: list[QuoteTick]
    dataset_hash: str
    start_time: datetime
    end_time: datetime


def _tick_round(value: Decimal, tick: Decimal) -> Decimal:
    return (value / tick).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN) * tick


def _row_string(ts_ns: int, o: Decimal, h: Decimal, lo: Decimal, c: Decimal, v: int) -> str:
    return f"{ts_ns}|{o}|{h}|{lo}|{c}|{v}"


def _hash_rows(rows: list[str]) -> str:
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()


def _rows_to_dataset(
    rows: list[tuple[int, Decimal, Decimal, Decimal, Decimal, int]],
    instrument: Instrument,
    spread: SpreadConfig,
    venue: Venue,
) -> Dataset:
    """Normalize rows into Nautilus bars + bid/ask quotes (spread-aware)."""
    nautilus_instrument_id = InstrumentId(symbol=Symbol(instrument.symbol), venue=venue)
    bar_type = BarType(
        instrument_id=nautilus_instrument_id,
        bar_spec=BarSpecification(1, BarAggregation.MINUTE, PriceType.MID),
    )
    tick = instrument.tick_size
    half = Decimal(spread.half_spread_ticks) * tick
    bars: list[Bar] = []
    quotes: list[QuoteTick] = []
    for ts_ns, o, h, lo, c, v in rows:
        bars.append(
            Bar(
                bar_type=bar_type,
                open=Price.from_str(str(o)),
                high=Price.from_str(str(h)),
                low=Price.from_str(str(lo)),
                close=Price.from_str(str(c)),
                volume=Quantity(v, 0),
                ts_event=ts_ns,
                ts_init=ts_ns,
            )
        )
        bid = max(c - half, tick)
        ask = c + half
        quotes.append(
            QuoteTick(
                instrument_id=nautilus_instrument_id,
                bid_price=Price.from_str(str(bid)),
                ask_price=Price.from_str(str(ask)),
                bid_size=Quantity(_QUOTE_SIZE, 0),
                ask_size=Quantity(_QUOTE_SIZE, 0),
                ts_event=ts_ns,
                ts_init=ts_ns,
            )
        )
    return Dataset(
        instrument_id=instrument.instrument_id,
        bars=bars,
        quotes=quotes,
        dataset_hash=_hash_rows([_row_string(*r) for r in rows]),
        start_time=unix_nanos_to_dt(rows[0][0]).astimezone(UTC),
        end_time=unix_nanos_to_dt(rows[-1][0]).astimezone(UTC),
    )


def synthetic_dataset(
    config: DatasetConfig, instrument: Instrument, spread: SpreadConfig, venue: Venue
) -> Dataset:
    """Seeded geometric random walk → OHLCV bars → bid/ask quotes (INV-3 safe)."""
    rng = random.Random(config.seed)
    tick = instrument.tick_size
    interval = timedelta(seconds=config.interval_seconds)
    start = datetime.fromisoformat(config.start_time_iso)
    dt_year = config.interval_seconds / (365 * 24 * 3600)
    sigma = config.annual_vol * sqrt(dt_year)

    rows: list[tuple[int, Decimal, Decimal, Decimal, Decimal, int]] = []
    prev_close = _tick_round(config.initial_mid, tick)
    for i in range(config.n_bars):
        ts_ns = dt_to_unix_nanos(start + i * interval)
        open_ = prev_close
        shock = exp(config.drift * dt_year + sigma * rng.gauss(0.0, 1.0))
        close = _tick_round(open_ * Decimal(str(shock)), tick)
        if close <= 0:
            close = tick
        high = max(open_, close) * Decimal(str(1.0 + rng.uniform(0.0, 0.0004)))
        low = min(open_, close) * Decimal(str(1.0 - rng.uniform(0.0, 0.0004)))
        high = max(_tick_round(high, tick), open_, close)
        low = min(_tick_round(low, tick), open_, close)
        if low <= 0:
            low = tick
        volume = rng.randint(10, 1000)
        rows.append((ts_ns, open_, high, low, close, volume))
        prev_close = close
    return _rows_to_dataset(rows, instrument, spread, venue)


def load_parquet_dataset(
    path: Path, config: DatasetConfig, instrument: Instrument, spread: SpreadConfig, venue: Venue
) -> Dataset:
    """Replay a historical parquet file (columns: ts_event, open, high, low, close, volume)."""
    import pyarrow.parquet as pq

    table = pq.read_table(path)
    columns = table.column_names
    for required in ("ts_event", "open", "high", "low", "close", "volume"):
        if required not in columns:
            raise ValueError(f"parquet dataset {path} is missing column {required!r}")
    rows: list[tuple[int, Decimal, Decimal, Decimal, Decimal, int]] = []
    for batch in table.to_batches():
        ts = batch.column("ts_event").to_pylist()
        o = batch.column("open").to_pylist()
        h = batch.column("high").to_pylist()
        lo = batch.column("low").to_pylist()
        c = batch.column("close").to_pylist()
        v = batch.column("volume").to_pylist()
        for ts_v, o_v, h_v, lo_v, c_v, v_v in zip(ts, o, h, lo, c, v, strict=True):
            ts_ns = int(ts_v)
            rows.append(
                (
                    ts_ns,
                    Decimal(str(o_v)),
                    Decimal(str(h_v)),
                    Decimal(str(lo_v)),
                    Decimal(str(c_v)),
                    int(v_v),
                )
            )
    rows.sort(key=lambda r: r[0])
    seen: set[int] = set()
    for r in rows:
        if r[0] in seen:
            raise ValueError(f"duplicate ts_event {r[0]} in {path}")
        seen.add(r[0])
    return _rows_to_dataset(rows, instrument, spread, venue)


def build_dataset(
    config: DatasetConfig, instrument: Instrument, spread: SpreadConfig, venue: Venue
) -> Dataset:
    """Dispatch to the configured dataset source."""
    if config.source == "synthetic":
        return synthetic_dataset(config, instrument, spread, venue)
    if config.source == "parquet":
        if config.path is None:
            raise ValueError("dataset.path is required when source='parquet'")
        return load_parquet_dataset(config.path, config, instrument, spread, venue)
    raise ValueError(f"unknown dataset source {config.source!r}")
