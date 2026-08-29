"""Market snapshot sources for the autonomous pipeline (Phase 7).

Two sources feed the pipeline:

- :class:`RepositorySnapshotSource` — the point-in-time repository
  (``adapters.market_data``), the production path once ingestion runs;
- :class:`SyntheticSnapshotSource` — a seeded, deterministic random walk that
  lets the whole pipeline operate unattended in PAPER mode before live feeds
  exist (dev/demo). Each ``(instrument, step)`` yields the same snapshot, so
  runs stay reproducible.

Both produce canonical :class:`MarketSnapshot` contracts with honest
``source`` provenance (INV-3).
"""

from __future__ import annotations

import random
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from typing import Protocol, cast

from core.clock.clocks import Clock, SystemClock
from core.domain.enums import Timeframe
from core.schemas import MarketSnapshot
from core.schemas.base import Provenance

__all__ = [
    "NoSnapshotError",
    "RepositorySnapshotSource",
    "SnapshotSource",
    "SyntheticSnapshotSource",
]

_PRODUCER = "apps.worker.sources"


class NoSnapshotError(RuntimeError):
    """Raised when no point-in-time snapshot is available for a cycle."""


class SnapshotSource(Protocol):
    def latest(self, instrument_id: str, *, now: datetime, step: int) -> MarketSnapshot: ...


class RepositorySnapshotSource:
    """Snapshots from the sealed market-data repository (INV-3 choke point)."""

    def __init__(self, repository: object, *, clock: Clock | None = None) -> None:
        self._repository = repository
        self._clock = clock or SystemClock()

    def latest(self, instrument_id: str, *, now: datetime, step: int) -> MarketSnapshot:
        repo = self._repository
        version = repo.latest_sealed_version(  # type: ignore[attr-defined]
            instrument_id=instrument_id, timeframe=self._timeframe()
        )
        if version is None:
            raise NoSnapshotError(f"no sealed dataset for {instrument_id}")
        snapshot = repo.snapshot(  # type: ignore[attr-defined]
            instrument_id=instrument_id,
            timeframe=self._timeframe(),
            as_of=now,
            dataset_version=version,
            clock=self._clock,
        )
        if snapshot is None:
            raise NoSnapshotError(f"no snapshot visible at {now.isoformat()} for {instrument_id}")
        return cast(MarketSnapshot, snapshot)

    @staticmethod
    def _timeframe() -> Timeframe:
        return Timeframe.M5


class SyntheticSnapshotSource:
    """Deterministic synthetic FX snapshots (seeded random walk per instrument).

    Intended for unattended PAPER operation without live feeds. Prices evolve
    as a bounded geometric walk; spreads are one tick around the mid.
    """

    def __init__(
        self,
        *,
        seed: int = 42,
        instruments: dict[str, Decimal] | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._seed = seed
        self._instruments = instruments or {}
        self._clock = clock or SystemClock()
        self._rngs: dict[str, random.Random] = {}
        self._last_mid: dict[str, Decimal] = {}

    def seed_mid(self, instrument_id: str, mid: Decimal) -> None:
        self._last_mid[instrument_id] = mid
        self._rngs[instrument_id] = random.Random(f"{self._seed}:{instrument_id}")

    def latest(self, instrument_id: str, *, now: datetime, step: int) -> MarketSnapshot:
        if instrument_id not in self._rngs:
            start = self._instruments.get(instrument_id, Decimal("1.10000"))
            self.seed_mid(instrument_id, start)
        rng = self._rngs[instrument_id]
        previous = self._last_mid[instrument_id]
        drift = rng.uniform(-0.0015, 0.0015)
        mid = previous * Decimal(str(1.0 + drift))
        self._last_mid[instrument_id] = mid

        tick = Decimal("0.00001")
        bid = (mid - tick).quantize(tick, rounding=ROUND_DOWN)
        ask = (mid + tick).quantize(tick, rounding=ROUND_DOWN)
        open_ = previous.quantize(tick, rounding=ROUND_DOWN)
        high = max(open_, mid) * Decimal("1.0004")
        low = min(open_, mid) * Decimal("0.9996")
        return MarketSnapshot(
            instrument_id=instrument_id,
            as_of=now,
            source_timestamp=now,
            bid=bid,
            ask=ask,
            last=mid.quantize(tick, rounding=ROUND_DOWN),
            open=open_,
            high=high.quantize(tick, rounding=ROUND_DOWN),
            low=low.quantize(tick, rounding=ROUND_DOWN),
            close=mid.quantize(tick, rounding=ROUND_DOWN),
            timeframe=Timeframe.M5,
            source=f"{_PRODUCER}:synthetic",
            produced_at=now,
            provenance=Provenance(producer=_PRODUCER, produced_at=now),
        )
