"""Test helper: assemble a full in-memory market data platform (Phase 1).

Used by unit, leakage and API tests — no MinIO/PostgreSQL required.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from adapters.market_data import (
    MarketDataPipeline,
    MarketDataRepository,
    MemoryCatalog,
    MemoryLayerStore,
)
from core.clock.clocks import VirtualClock
from core.schemas.market_data import RawMarketRecord

from factories import FIXED_START


class Platform:
    """In-memory pipeline + repository over one shared VirtualClock."""

    def __init__(self, start: datetime = FIXED_START) -> None:
        self.clock = VirtualClock(start)
        self.store = MemoryLayerStore()
        self.catalog = MemoryCatalog()
        self.pipeline = MarketDataPipeline(self.store, self.catalog, self.clock)
        self.repository = MarketDataRepository(self.store, self.catalog)


def make_minute_raw_records(
    source: str,
    start: datetime,
    count: int,
    *,
    available_lag: timedelta = timedelta(seconds=0),
    ingested_at: datetime | None = None,
    symbol: str = "EUR/USD",
    open_price: Decimal = Decimal("1.08000"),
) -> tuple[RawMarketRecord, ...]:
    """``count`` M1 OHLCV raw records starting at ``start``, one per minute."""
    records: list[RawMarketRecord] = []
    for index in range(count):
        event = start + timedelta(minutes=index)
        open_price_i = open_price + Decimal("0.00005") * index
        records.append(
            RawMarketRecord(
                source=source,
                source_record_id=f"{source}-{event.isoformat()}",
                event_time=event,
                available_time=event + available_lag,
                ingested_at=ingested_at or event,
                payload={
                    "symbol": symbol,
                    "timeframe": "1m",
                    "open": str(open_price_i),
                    "high": str(open_price_i + Decimal("0.00010")),
                    "low": str(open_price_i - Decimal("0.00010")),
                    "close": str(open_price_i + Decimal("0.00005")),
                    "volume": "1000",
                },
            )
        )
    return tuple(records)


def ingest_and_seal(
    platform: Platform,
    source: str,
    instrument_id: str,
    timeframe: str = "M1",
    *,
    raw_records: tuple[RawMarketRecord, ...] | None = None,
    start: datetime | None = None,
    count: int = 5,
) -> int:
    """Run one ingestion and seal dataset version 1; returns the version number."""
    from core.domain.enums import Timeframe  # local import keeps helper lean

    records = raw_records or make_minute_raw_records(source, start or platform.clock.now(), count)
    platform.pipeline.ingest(source, records, timeframe=Timeframe(timeframe))
    return platform.pipeline.seal(instrument_id, Timeframe(timeframe), version=1).version
