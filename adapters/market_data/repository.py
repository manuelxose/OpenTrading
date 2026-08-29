"""Point-in-time query layer over sealed gold datasets (INV-3, Phase 1 DoD).

This is the **only** supported read path for market data:

- :class:`PointInTimeFilter` — single choke point that drops every row with
  ``available_time > as_of`` or ``event_time > as_of`` before anything else;
- :class:`MarketDataRepository` — loads gold partitions, verifies their
  checksums against the manifest (immutability proof), filters, and serves
  bars / :class:`~core.schemas.market.MarketSnapshot`.

Future information is impossible to retrieve through the normal query API:
every public method requires an explicit ``as_of`` and goes through the filter,
and raw Parquet access is private. The leakage suite proves both properties.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from core.clock.clocks import Clock
from core.domain.enums import DatasetState, LayerName, Timeframe
from core.schemas.base import ensure_utc
from core.schemas.market import MarketSnapshot
from core.schemas.market_data import Bar, DatasetVersion, dataset_id_for

from adapters.market_data.catalog import Catalog
from adapters.market_data.errors import (
    DatasetNotFoundError,
    DatasetNotSealedError,
    DatasetSealedError,
    FutureDataLeakageError,
)
from adapters.market_data.hashing import bar_row_key, dataset_hash, partition_hash
from adapters.market_data.snapshot import snapshot_from_bar
from adapters.market_data.storage import LayerStore, manifest_key

__all__ = ["MarketDataRepository", "PointInTimeFilter"]


class PointInTimeFilter:
    """The single INV-3 choke point.

    Dropping logic in exactly one place makes the absolute invariant auditable:
    **no record with available_time > as_of may appear in a query result.**
    """

    def __init__(self, as_of: datetime) -> None:
        self._as_of = ensure_utc(as_of)

    @property
    def as_of(self) -> datetime:
        return self._as_of

    def apply(self, bars: Iterable[Bar]) -> tuple[Bar, ...]:
        return tuple(
            bar
            for bar in bars
            if bar.available_time <= self._as_of and bar.event_time <= self._as_of
        )


class MarketDataRepository:
    """Read-only query API over sealed gold dataset versions."""

    def __init__(self, store: LayerStore, catalog: Catalog) -> None:
        self._store = store
        self._catalog = catalog

    # ── Dataset resolution ───────────────────────────────────────────────────
    def _sealed_dataset(
        self, instrument_id: str, timeframe: Timeframe, dataset_version: int
    ) -> DatasetVersion:
        dataset_id = dataset_id_for(instrument_id, timeframe)
        dataset = self._catalog.get_dataset(dataset_id, dataset_version)
        if dataset is None:
            raise DatasetNotFoundError(f"dataset {dataset_id} v{dataset_version} not found")
        if dataset.state is not DatasetState.SEALED:
            raise DatasetNotSealedError(
                f"dataset {dataset_id} v{dataset_version} is {dataset.state.value}, not SEALED"
            )
        return dataset

    def latest_sealed_version(
        self, instrument_id: str, timeframe: Timeframe
    ) -> DatasetVersion | None:
        return self._catalog.latest_sealed(dataset_id_for(instrument_id, timeframe))

    # ── Gold loading with immutability proof ─────────────────────────────────
    def _load_gold(self, dataset: DatasetVersion) -> tuple[Bar, ...]:
        """Load every partition, verify partition checksums and the dataset hash."""
        manifest = self._store.read_json(
            LayerName.GOLD,
            manifest_key(
                dataset.data_class, dataset.instrument_id, dataset.timeframe, dataset.version
            ),
        )
        if manifest.get("dataset_hash") != dataset.dataset_hash:
            raise DatasetSealedError("gold manifest hash does not match the catalog entry")
        rows: list[Bar] = []
        for part in dataset.partitions:
            part_rows = self._store.read_bars(LayerName.GOLD, part.object_key)
            if len(part_rows) != part.row_count:
                raise DatasetSealedError(
                    f"partition {part.object_key}: manifest says {part.row_count} rows, "
                    f"object holds {len(part_rows)} (immutability violated)"
                )
            if partition_hash(part_rows) != part.checksum:
                raise DatasetSealedError(
                    f"partition {part.object_key} checksum mismatch (immutability violated)"
                )
            rows.extend(part_rows)
        if dataset_hash(rows) != dataset.dataset_hash:
            raise DatasetSealedError("dataset hash mismatch (immutability violated)")
        return tuple(sorted(rows, key=bar_row_key))

    # ── Query API ────────────────────────────────────────────────────────────
    def bars(
        self,
        *,
        instrument_id: str,
        timeframe: Timeframe,
        as_of: datetime,
        dataset_version: int,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> tuple[Bar, ...]:
        """Bars of a sealed dataset visible at ``as_of`` (INV-3 filter applied).

        ``start``/``end`` bound ``event_time`` (inclusive) for convenience; the
        point-in-time filter is applied first and can never be disabled.
        """
        dataset = self._sealed_dataset(instrument_id, timeframe, dataset_version)
        rows = self._load_gold(dataset)
        filtered = PointInTimeFilter(as_of).apply(rows)
        if start is not None:
            start_utc = ensure_utc(start)
            filtered = tuple(bar for bar in filtered if bar.event_time >= start_utc)
        if end is not None:
            end_utc = ensure_utc(end)
            filtered = tuple(bar for bar in filtered if bar.event_time <= end_utc)
        _assert_no_future_rows(filtered, as_of)
        return filtered

    def snapshot(
        self,
        *,
        instrument_id: str,
        timeframe: Timeframe,
        as_of: datetime,
        dataset_version: int,
        clock: Clock,
    ) -> MarketSnapshot | None:
        """Point-in-time snapshot from the latest bar visible at ``as_of``.

        Returns ``None`` when no bar is visible yet. The absolute invariant is
        enforced twice: by the :class:`PointInTimeFilter` and by the derivation
        guard in :func:`snapshot_from_bar`.
        """
        visible = self.bars(
            instrument_id=instrument_id,
            timeframe=timeframe,
            as_of=as_of,
            dataset_version=dataset_version,
        )
        if not visible:
            return None
        latest = max(visible, key=lambda bar: (bar.event_time, bar.source_record_id))
        return snapshot_from_bar(
            latest,
            as_of=as_of,
            clock=clock,
            dataset_id=dataset_id_for(instrument_id, timeframe),
            dataset_version=dataset_version,
        )


def _assert_no_future_rows(bars: tuple[Bar, ...], as_of: datetime) -> None:
    """Defense-in-depth: fail loudly if the filter was bypassed anywhere."""
    as_of_utc = ensure_utc(as_of)
    for bar in bars:
        if bar.available_time > as_of_utc or bar.event_time > as_of_utc:
            raise FutureDataLeakageError(
                f"row {bar.source_record_id!r} posterior to as_of={as_of_utc.isoformat()} "
                f"reached the query surface (INV-3)"
            )
