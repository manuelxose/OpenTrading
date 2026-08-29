"""MarketSnapshot generation with an explicit ``as_of`` (INV-3).

OHLCV bars carry no bid/ask, so the derivation uses the documented zero-spread
assumption ``bid = ask = close`` (mid = close). This is the deterministic
contract Phase 2+ consumers (TradingAgents, Graphiti, Nautilus) depend on.

Defense in depth: even though :class:`MarketDataRepository` already filters
``available_time <= as_of`` before this function is ever reached, the guard is
repeated here so a future caller cannot bypass the invariant.
"""

from __future__ import annotations

from datetime import datetime

from core.clock.clocks import Clock
from core.schemas.base import Provenance, ensure_utc
from core.schemas.market import MarketSnapshot
from core.schemas.market_data import Bar

from adapters.market_data.errors import FutureDataLeakageError

__all__ = ["snapshot_from_bar"]

#: Producer tag recorded in snapshot provenance.
_PRODUCER = "adapters.market_data.snapshot"


def snapshot_from_bar(
    bar: Bar,
    *,
    as_of: datetime,
    clock: Clock,
    dataset_id: str,
    dataset_version: int,
) -> MarketSnapshot:
    """Derive the point-in-time snapshot for the latest bar visible at ``as_of``.

    Raises :class:`FutureDataLeakageError` if the bar is posterior to ``as_of``
    (available_time or event_time) — this must never happen through the normal
    query API, and the guard makes a bypass fail loudly instead of silently.
    """
    as_of_utc = ensure_utc(as_of)
    if bar.available_time > as_of_utc or bar.event_time > as_of_utc:
        raise FutureDataLeakageError(
            f"bar {bar.source_record_id!r} has available_time={bar.available_time.isoformat()}, "
            f"event_time={bar.event_time.isoformat()} but as_of={as_of_utc.isoformat()} (INV-3)"
        )
    now = clock.now()
    return MarketSnapshot(
        instrument_id=bar.instrument_id,
        as_of=as_of_utc,
        source_timestamp=bar.event_time,
        bid=bar.close,
        ask=bar.close,
        last=bar.close,
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=bar.volume,
        timeframe=bar.timeframe,
        source=bar.source,
        produced_at=now,
        provenance=Provenance(
            producer=_PRODUCER,
            produced_at=now,
            source_ids={
                "dataset_id": dataset_id,
                "dataset_version": str(dataset_version),
                "bar_checksum": bar.checksum or "",
            },
            notes={"spread_assumption": "zero (OHLCV-derived bid=ask=close)"},
        ),
    )
