"""Medallion ingestion pipeline: RAW → BRONZE → SILVER → GOLD.

- :meth:`MarketDataPipeline.ingest` writes raw, normalizes to bronze
  (instrument + timezone), then produces flagged/deduplicated silver bars and
  gap records for one ingestion run.
- :meth:`MarketDataPipeline.seal` merges silver into one immutable gold dataset
  version with a deterministic content hash and partition manifest.

Fundamentals, macro and news reuse the same flow later: they only add payload
mappers per :class:`~core.domain.enums.MarketDataClass`, not new layers.
"""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import suppress
from datetime import datetime, timedelta

from core.clock.clocks import Clock
from core.domain.enums import (
    DataQualityFlag,
    IngestionStatus,
    LayerName,
    MarketDataClass,
    Timeframe,
)
from core.schemas.market_data import (
    Bar,
    BarGap,
    DatasetPartition,
    DatasetVersion,
    IngestionRun,
    RawMarketRecord,
    dataset_id_for,
)

from adapters.market_data.catalog import Catalog
from adapters.market_data.errors import MarketDataError
from adapters.market_data.hashing import (
    bar_checksum,
    bar_row_key,
    canonical_bar_bytes,
    dataset_hash,
    partition_hash,
)
from adapters.market_data.normalization import (
    BarPayloadMapper,
    SymbolNormalizer,
    build_bar_from_payload,
    parse_timeframe,
)
from adapters.market_data.quality import DataQualityEngine
from adapters.market_data.storage import (
    LayerStore,
    gold_part_key,
    manifest_key,
    raw_key,
    run_bars_key,
)

__all__ = ["MarketDataPipeline"]


class MarketDataPipeline:
    """Deterministic raw→bronze→silver→gold pipeline (Phase 1 DoD)."""

    def __init__(
        self,
        store: LayerStore,
        catalog: Catalog,
        clock: Clock,
        *,
        normalizer: SymbolNormalizer | None = None,
        quality_engine: DataQualityEngine | None = None,
        stale_after: timedelta | None = None,
    ) -> None:
        self._store = store
        self._catalog = catalog
        self._clock = clock
        self._normalizer = normalizer or SymbolNormalizer()
        self._quality = quality_engine or DataQualityEngine(stale_after or timedelta(hours=1))

    # ── RAW → BRONZE → SILVER ────────────────────────────────────────────────
    def ingest(
        self,
        source: str,
        records: Sequence[RawMarketRecord],
        *,
        timeframe: Timeframe | None = None,
    ) -> IngestionRun:
        """Ingest one batch: raw storage, bronze normalization, silver quality.

        A single run handles exactly one :class:`MarketDataClass` (the first
        record's; mixed batches are rejected so runs stay auditable).
        """
        if not records:
            raise MarketDataError("cannot ingest an empty batch")
        data_class = records[0].data_class
        if any(record.data_class is not data_class for record in records):
            raise MarketDataError("one ingestion run must carry a single data_class")

        started_at = self._clock.now()
        run_id = self._catalog.start_run(source, data_class, started_at)
        stats: dict[str, int] = {}
        try:
            raw_records = tuple(records)
            ingested_at = self._clock.now()
            self._store.write_raw(raw_key(source, data_class, str(run_id)), raw_records)
            stats["raw_records"] = len(raw_records)

            bronze = self._to_bronze(raw_records, source, data_class, ingested_at, timeframe)
            stats["bronze_bars"] = len(bronze)
            for (instrument_id, tf), group in _group_bars(bronze).items():
                self._store.write_bars(
                    LayerName.BRONZE,
                    run_bars_key(data_class, instrument_id, tf, str(run_id)),
                    tuple(group),
                )

            silver: list[Bar] = []
            gaps: list[BarGap] = []
            for (instrument_id, tf), group in _group_bars(bronze).items():
                outcome = self._quality.process(tuple(group), self._clock)
                silver.extend(outcome.silver_bars)
                gaps.extend(outcome.gaps)
                self._store.write_bars(
                    LayerName.SILVER,
                    run_bars_key(data_class, instrument_id, tf, str(run_id)),
                    outcome.silver_bars,
                )
            stats["silver_bars"] = len(silver)
            stats["duplicates"] = sum(
                1 for bar in silver if DataQualityFlag.DUPLICATE in bar.quality_flags
            )
            stats["gaps"] = len(gaps)
            stats["stale"] = sum(1 for bar in silver if DataQualityFlag.STALE in bar.quality_flags)
            stats["anomalies"] = sum(
                1 for bar in silver if DataQualityFlag.PRICE_ANOMALY in bar.quality_flags
            )
            stats["future_dated"] = sum(
                1 for bar in silver if DataQualityFlag.FUTURE_DATED in bar.quality_flags
            )

            finished_at = self._clock.now()
            self._catalog.register_gaps(run_id, tuple(gaps))
            self._catalog.finish_run(run_id, IngestionStatus.SUCCEEDED, stats, finished_at)
            return IngestionRun(
                run_id=run_id,
                source=source,
                data_class=data_class,
                status=IngestionStatus.SUCCEEDED,
                started_at=started_at,
                finished_at=finished_at,
                stats=stats,
                gaps=tuple(gaps),
            )
        except Exception as exc:
            with suppress(Exception):
                self._catalog.finish_run(
                    run_id, IngestionStatus.FAILED, stats, self._clock.now(), error=str(exc)
                )
            raise

    def _to_bronze(
        self,
        raw_records: tuple[RawMarketRecord, ...],
        source: str,
        data_class: MarketDataClass,
        ingested_at: datetime,
        timeframe: Timeframe | None,
    ) -> tuple[Bar, ...]:
        mapper = BarPayloadMapper()
        bars: list[Bar] = []
        for record in raw_records:
            payload = record.payload
            symbol = mapper.get(payload, "symbol")
            instrument_id = self._normalizer.normalize(str(symbol))
            record_timeframe = parse_timeframe(mapper.get(payload, "timeframe"))
            resolved_timeframe = record_timeframe or timeframe
            if resolved_timeframe is None:
                raise MarketDataError(
                    f"record {record.source_record_id!r} has no timeframe "
                    "(payload or ingest default)"
                )
            inferred_available = record.available_time is None
            available_time = (
                record.available_time if record.available_time is not None else ingested_at
            )
            bar = build_bar_from_payload(
                payload,
                source=source,
                source_record_id=record.source_record_id,
                event_time=record.event_time,
                available_time=available_time,
                ingested_at=ingested_at,
                instrument_id=instrument_id,
                timeframe=resolved_timeframe,
            )
            if inferred_available:
                flags = tuple(
                    sorted(
                        (*bar.quality_flags, DataQualityFlag.AVAILABLE_TIME_INFERRED),
                        key=lambda flag: flag.value,
                    )
                )
                bar = bar.model_copy(update={"quality_flags": flags})
            bars.append(bar)
        return tuple(bars)

    # ── GOLD ─────────────────────────────────────────────────────────────────
    def seal(
        self,
        instrument_id: str,
        timeframe: Timeframe,
        version: int,
        *,
        data_class: MarketDataClass = MarketDataClass.OHLCV,
    ) -> DatasetVersion:
        """Build one immutable gold dataset version from all silver runs.

        Deterministic by construction: rows are ordered by
        ``(event_time, instrument_id, timeframe, source_record_id)``, every row
        and partition gets a content checksum, and the whole dataset gets one
        SHA-256 ``dataset_hash`` stored both in PostgreSQL and in the gold
        manifest.
        """
        dataset_id = dataset_id_for(instrument_id, timeframe)
        prefix = f"{data_class.value}/{instrument_id}/{timeframe.value}/run="
        all_bars: list[Bar] = []
        for key in self._store.list_keys(LayerName.SILVER, prefix):
            all_bars.extend(self._store.read_bars(LayerName.SILVER, key))
        if not all_bars:
            raise MarketDataError(f"no silver data to seal for {dataset_id} v{version}")

        # Cross-run merge: one row per identity; when duplicates exist the
        # non-DUPLICATE row wins (deterministic content tiebreaker).
        gold_rows = list(_merge_gold_rows(tuple(all_bars)))
        if not gold_rows:
            raise MarketDataError(f"no silver rows to seal for {dataset_id} v{version}")
        gold_rows.sort(key=bar_row_key)

        rows_with_checksums = [
            bar if bar.checksum else bar.model_copy(update={"checksum": bar_checksum(bar)})
            for bar in gold_rows
        ]
        digest = dataset_hash(rows_with_checksums)

        self._catalog.open_dataset(
            dataset_id, instrument_id, data_class, timeframe, version, self._clock.now()
        )

        partitions: list[DatasetPartition] = []
        month_groups: dict[tuple[int, int], list[Bar]] = {}
        for bar in rows_with_checksums:
            month_groups.setdefault((bar.event_time.year, bar.event_time.month), []).append(bar)
        for (year, month), rows in sorted(month_groups.items()):
            key = gold_part_key(data_class, instrument_id, timeframe, version, year, month, 0)
            self._store.write_bars(LayerName.GOLD, key, tuple(rows))
            partitions.append(
                DatasetPartition(object_key=key, row_count=len(rows), checksum=partition_hash(rows))
            )

        sealed_at = self._clock.now()
        manifest = {
            "dataset_id": dataset_id,
            "version": version,
            "instrument_id": instrument_id,
            "timeframe": timeframe.value,
            "data_class": data_class.value,
            "dataset_hash": digest,
            "row_count": len(rows_with_checksums),
            "event_time_min": rows_with_checksums[0].event_time.isoformat(),
            "event_time_max": rows_with_checksums[-1].event_time.isoformat(),
            "available_time_max": max(
                bar.available_time for bar in rows_with_checksums
            ).isoformat(),
            "sealed_at": sealed_at.isoformat(),
            "partitions": [
                {
                    "object_key": part.object_key,
                    "row_count": part.row_count,
                    "checksum": part.checksum,
                }
                for part in partitions
            ],
        }
        self._store.write_json(
            LayerName.GOLD,
            manifest_key(data_class, instrument_id, timeframe, version),
            manifest,
        )
        return self._catalog.seal_dataset(
            dataset_id,
            version,
            dataset_hash=digest,
            row_count=len(rows_with_checksums),
            event_min=rows_with_checksums[0].event_time,
            event_max=rows_with_checksums[-1].event_time,
            avail_max=max(bar.available_time for bar in rows_with_checksums),
            sealed_at=sealed_at,
            partitions=tuple(partitions),
        )


def _group_bars(bars: Sequence[Bar]) -> dict[tuple[str, Timeframe], list[Bar]]:
    grouped: dict[tuple[str, Timeframe], list[Bar]] = {}
    for bar in bars:
        grouped.setdefault((bar.instrument_id, bar.timeframe), []).append(bar)
    return grouped


def _merge_gold_rows(bars: tuple[Bar, ...]) -> tuple[Bar, ...]:
    """Deterministic cross-run merge for gold: one row per bar identity.

    Identity: ``(instrument_id, timeframe, event_time, source, source_record_id)``.
    The survivor is the first non-DUPLICATE candidate (content bytes as a
    deterministic tiebreaker); rows already flagged DUPLICATE in silver only
    survive when every candidate for that identity is duplicate-flagged.
    """
    groups: dict[tuple[str, Timeframe, datetime, str, str], list[Bar]] = {}
    for bar in bars:
        identity = (
            bar.instrument_id,
            bar.timeframe,
            bar.event_time,
            bar.source,
            bar.source_record_id,
        )
        groups.setdefault(identity, []).append(bar)
    survivors: list[Bar] = []
    for identity in sorted(groups):
        candidates = sorted(
            groups[identity],
            key=lambda bar: (
                DataQualityFlag.DUPLICATE in bar.quality_flags,
                canonical_bar_bytes(bar),
            ),
        )
        survivors.append(candidates[0])
    return tuple(survivors)
