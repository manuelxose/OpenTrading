"""Market data catalog: PostgreSQL-backed (ADR-0010) or in-memory.

The catalog owns metadata/state — instruments, ingestion runs, gold dataset
versions and partitions — while bars live in Parquet/MinIO (ADR-0011). Sealed
dataset versions are immutable: :class:`DatasetSealedError` guards any attempt
to re-seal or overwrite.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol
from uuid import UUID

from core.config.settings import ensure_psycopg_dsn
from core.domain.enums import (
    AssetClass,
    DatasetState,
    IngestionStatus,
    MarketDataClass,
    Timeframe,
)
from core.schemas.base import Provenance
from core.schemas.market import Instrument
from core.schemas.market_data import BarGap, DatasetPartition, DatasetVersion, IngestionRun
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from adapters.market_data.catalog_db import (
    bar_gaps_table,
    dataset_partitions_table,
    dataset_versions_table,
    ingestion_runs_table,
    instruments_table,
)
from adapters.market_data.errors import (
    DatasetNotFoundError,
    DatasetSealedError,
    DatasetVersionExistsError,
)

__all__ = ["Catalog", "MemoryCatalog", "PostgresCatalog"]

#: Provenance marker for instruments reconstructed from the catalog.
_RECONSTRUCTED_PRODUCER = "adapters.market_data.catalog"


class Catalog(Protocol):
    """Metadata/state store for the market data platform."""

    def ensure_instrument(
        self, instrument: Instrument, source: str, created_at: datetime
    ) -> str: ...

    def get_instrument(self, instrument_id: str) -> Instrument | None: ...

    def list_instruments(self) -> tuple[Instrument, ...]: ...

    def start_run(self, source: str, data_class: MarketDataClass, started_at: datetime) -> UUID: ...

    def finish_run(
        self,
        run_id: UUID,
        status: IngestionStatus,
        stats: dict[str, int],
        finished_at: datetime,
        error: str | None = None,
    ) -> None: ...

    def register_gaps(self, run_id: UUID, gaps: tuple[BarGap, ...]) -> None: ...

    def open_dataset(
        self,
        dataset_id: str,
        instrument_id: str,
        data_class: MarketDataClass,
        timeframe: Timeframe,
        version: int,
        opened_at: datetime,
    ) -> DatasetVersion: ...

    def seal_dataset(
        self,
        dataset_id: str,
        version: int,
        *,
        dataset_hash: str,
        row_count: int,
        event_min: datetime,
        event_max: datetime,
        avail_max: datetime,
        sealed_at: datetime,
        partitions: tuple[DatasetPartition, ...],
    ) -> DatasetVersion: ...

    def get_dataset(self, dataset_id: str, version: int) -> DatasetVersion | None: ...

    def latest_sealed(self, dataset_id: str) -> DatasetVersion | None: ...


class MemoryCatalog:
    """Deterministic in-memory catalog (unit and leakage tests)."""

    def __init__(self) -> None:
        self._instruments: dict[str, Instrument] = {}
        self._runs: dict[UUID, IngestionRun] = {}
        self._gaps: dict[UUID, tuple[BarGap, ...]] = {}
        self._versions: dict[tuple[str, int], DatasetVersion] = {}

    def ensure_instrument(self, instrument: Instrument, source: str, created_at: datetime) -> str:
        if instrument.instrument_id not in self._instruments:
            self._instruments[instrument.instrument_id] = instrument
        return instrument.instrument_id

    def get_instrument(self, instrument_id: str) -> Instrument | None:
        return self._instruments.get(instrument_id)

    def list_instruments(self) -> tuple[Instrument, ...]:
        return tuple(sorted(self._instruments.values(), key=lambda i: i.instrument_id))

    def start_run(self, source: str, data_class: MarketDataClass, started_at: datetime) -> UUID:
        run = IngestionRun(
            source=source,
            data_class=data_class,
            status=IngestionStatus.STARTED,
            started_at=started_at,
        )
        self._runs[run.run_id] = run
        return run.run_id

    def finish_run(
        self,
        run_id: UUID,
        status: IngestionStatus,
        stats: dict[str, int],
        finished_at: datetime,
        error: str | None = None,
    ) -> None:
        run = self._runs[run_id]
        self._runs[run_id] = run.model_copy(
            update={
                "status": status,
                "stats": dict(stats),
                "finished_at": finished_at,
                "error": error,
            }
        )

    def register_gaps(self, run_id: UUID, gaps: tuple[BarGap, ...]) -> None:
        self._gaps[run_id] = tuple(gaps)

    def open_dataset(
        self,
        dataset_id: str,
        instrument_id: str,
        data_class: MarketDataClass,
        timeframe: Timeframe,
        version: int,
        opened_at: datetime,
    ) -> DatasetVersion:
        key = (dataset_id, version)
        if key in self._versions:
            raise DatasetVersionExistsError(f"dataset version {dataset_id} v{version} exists")
        version_obj = DatasetVersion(
            dataset_id=dataset_id,
            version=version,
            instrument_id=instrument_id,
            data_class=data_class,
            timeframe=timeframe,
            state=DatasetState.OPEN,
        )
        self._versions[key] = version_obj
        return version_obj

    def seal_dataset(
        self,
        dataset_id: str,
        version: int,
        *,
        dataset_hash: str,
        row_count: int,
        event_min: datetime,
        event_max: datetime,
        avail_max: datetime,
        sealed_at: datetime,
        partitions: tuple[DatasetPartition, ...],
    ) -> DatasetVersion:
        key = (dataset_id, version)
        current = self._versions.get(key)
        if current is None:
            raise DatasetNotFoundError(f"dataset version {dataset_id} v{version} not found")
        if current.state is DatasetState.SEALED:
            raise DatasetSealedError(f"dataset version {dataset_id} v{version} is sealed")
        sealed = current.model_copy(
            update={
                "state": DatasetState.SEALED,
                "dataset_hash": dataset_hash,
                "row_count": row_count,
                "event_time_min": event_min,
                "event_time_max": event_max,
                "available_time_max": avail_max,
                "sealed_at": sealed_at,
                "partitions": tuple(partitions),
            }
        )
        self._versions[key] = sealed
        return sealed

    def get_dataset(self, dataset_id: str, version: int) -> DatasetVersion | None:
        return self._versions.get((dataset_id, version))

    def latest_sealed(self, dataset_id: str) -> DatasetVersion | None:
        sealed = [
            v
            for (ds_id, _version), v in self._versions.items()
            if ds_id == dataset_id and v.state is DatasetState.SEALED
        ]
        if not sealed:
            return None
        return max(sealed, key=lambda v: v.version)


def _instrument_from_row(row: Any) -> Instrument:
    created_at: datetime = row.created_at
    return Instrument(
        instrument_id=row.instrument_id,
        symbol=row.symbol,
        exchange=row.exchange,
        asset_class=AssetClass(row.asset_class),
        base_currency=row.base_currency,
        quote_currency=row.quote_currency,
        price_precision=int(row.price_precision),
        tick_size=Decimal(row.tick_size),
        lot_size=Decimal(row.lot_size),
        lot_step=Decimal(row.lot_step),
        min_lot=Decimal(row.min_lot),
        max_lot=Decimal(row.max_lot),
        contract_size=Decimal(row.contract_size),
        is_active=bool(row.is_active),
        produced_at=created_at,
        provenance=Provenance(
            producer=_RECONSTRUCTED_PRODUCER,
            produced_at=created_at,
            notes={"reconstructed_from": "postgres catalog"},
        ),
    )


class PostgresCatalog:
    """PostgreSQL-backed catalog (ADR-0010); metadata only, bars stay in MinIO."""

    def __init__(self, dsn: str) -> None:
        self._engine: Engine = create_engine(ensure_psycopg_dsn(dsn))

    # ── Instruments ──────────────────────────────────────────────────────────
    def ensure_instrument(self, instrument: Instrument, source: str, created_at: datetime) -> str:
        with self._engine.begin() as conn:
            conn.execute(
                pg_insert(instruments_table)
                .values(
                    instrument_id=instrument.instrument_id,
                    symbol=instrument.symbol,
                    exchange=instrument.exchange,
                    asset_class=instrument.asset_class.value,
                    base_currency=instrument.base_currency,
                    quote_currency=instrument.quote_currency,
                    price_precision=instrument.price_precision,
                    tick_size=instrument.tick_size,
                    lot_size=instrument.lot_size,
                    lot_step=instrument.lot_step,
                    min_lot=instrument.min_lot,
                    max_lot=instrument.max_lot,
                    contract_size=instrument.contract_size,
                    is_active=instrument.is_active,
                    source=source,
                    created_at=created_at,
                )
                .on_conflict_do_nothing(index_elements=["instrument_id"])
            )
        return instrument.instrument_id

    def get_instrument(self, instrument_id: str) -> Instrument | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(instruments_table).where(instruments_table.c.instrument_id == instrument_id)
            ).first()
        return _instrument_from_row(row) if row is not None else None

    def list_instruments(self) -> tuple[Instrument, ...]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(instruments_table).order_by(instruments_table.c.instrument_id)
            )
            instruments = tuple(_instrument_from_row(row) for row in rows)
        return instruments

    # ── Ingestion runs ───────────────────────────────────────────────────────
    def start_run(self, source: str, data_class: MarketDataClass, started_at: datetime) -> UUID:
        run_id = uuid.uuid4()
        with self._engine.begin() as conn:
            conn.execute(
                ingestion_runs_table.insert().values(
                    run_id=run_id,
                    source=source,
                    data_class=data_class.value,
                    status=IngestionStatus.STARTED.value,
                    started_at=started_at,
                )
            )
        return run_id

    def finish_run(
        self,
        run_id: UUID,
        status: IngestionStatus,
        stats: dict[str, int],
        finished_at: datetime,
        error: str | None = None,
    ) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                ingestion_runs_table.update()
                .where(ingestion_runs_table.c.run_id == run_id)
                .values(
                    status=status.value,
                    stats=dict(stats),
                    finished_at=finished_at,
                    error=error,
                )
            )

    def register_gaps(self, run_id: UUID, gaps: tuple[BarGap, ...]) -> None:
        if not gaps:
            return
        with self._engine.begin() as conn:
            for gap in gaps:
                conn.execute(
                    bar_gaps_table.insert().values(
                        ingestion_run_id=run_id,
                        instrument_id=gap.instrument_id,
                        timeframe=gap.timeframe.value,
                        expected_time=gap.expected_time,
                        previous_time=gap.previous_time,
                        next_time=gap.next_time,
                        detected_at=gap.detected_at,
                    )
                )

    # ── Dataset versions ─────────────────────────────────────────────────────
    def open_dataset(
        self,
        dataset_id: str,
        instrument_id: str,
        data_class: MarketDataClass,
        timeframe: Timeframe,
        version: int,
        opened_at: datetime,
    ) -> DatasetVersion:
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    dataset_versions_table.insert().values(
                        dataset_id=dataset_id,
                        version=version,
                        instrument_id=instrument_id,
                        data_class=data_class.value,
                        timeframe=timeframe.value,
                        state=DatasetState.OPEN.value,
                        opened_at=opened_at,
                    )
                )
        except IntegrityError as exc:
            raise DatasetVersionExistsError(
                f"dataset version {dataset_id} v{version} already exists"
            ) from exc
        opened = self.get_dataset(dataset_id, version)
        assert opened is not None  # inserted above
        return opened

    def seal_dataset(
        self,
        dataset_id: str,
        version: int,
        *,
        dataset_hash: str,
        row_count: int,
        event_min: datetime,
        event_max: datetime,
        avail_max: datetime,
        sealed_at: datetime,
        partitions: tuple[DatasetPartition, ...],
    ) -> DatasetVersion:
        with self._engine.begin() as conn:
            result = conn.execute(
                dataset_versions_table.update()
                .where(
                    dataset_versions_table.c.dataset_id == dataset_id,
                    dataset_versions_table.c.version == version,
                    dataset_versions_table.c.state == DatasetState.OPEN.value,
                )
                .values(
                    state=DatasetState.SEALED.value,
                    dataset_hash=dataset_hash,
                    row_count=row_count,
                    event_time_min=event_min,
                    event_time_max=event_max,
                    available_time_max=avail_max,
                    sealed_at=sealed_at,
                )
                .returning(dataset_versions_table.c.id)
            )
            version_row_id = result.scalar_one_or_none()
            if version_row_id is None:
                existing = conn.execute(
                    select(dataset_versions_table.c.id).where(
                        dataset_versions_table.c.dataset_id == dataset_id,
                        dataset_versions_table.c.version == version,
                    )
                ).first()
                if existing is None:
                    raise DatasetNotFoundError(f"dataset version {dataset_id} v{version} not found")
                raise DatasetSealedError(f"dataset version {dataset_id} v{version} is sealed")
            for part in partitions:
                conn.execute(
                    dataset_partitions_table.insert().values(
                        dataset_version_id=version_row_id,
                        object_key=part.object_key,
                        row_count=part.row_count,
                        checksum=part.checksum,
                    )
                )
        sealed = self.get_dataset(dataset_id, version)
        assert sealed is not None
        return sealed

    def get_dataset(self, dataset_id: str, version: int) -> DatasetVersion | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(dataset_versions_table).where(
                    dataset_versions_table.c.dataset_id == dataset_id,
                    dataset_versions_table.c.version == version,
                )
            ).first()
            if row is None:
                return None
            part_rows = conn.execute(
                select(dataset_partitions_table)
                .where(dataset_partitions_table.c.dataset_version_id == row.id)
                .order_by(dataset_partitions_table.c.object_key)
            )
            partitions = tuple(
                DatasetPartition(
                    object_key=part.object_key,
                    row_count=int(part.row_count),
                    checksum=part.checksum,
                )
                for part in part_rows
            )
        return DatasetVersion(
            dataset_id=row.dataset_id,
            version=int(row.version),
            instrument_id=row.instrument_id,
            data_class=MarketDataClass(row.data_class),
            timeframe=Timeframe(row.timeframe),
            state=DatasetState(row.state),
            dataset_hash=row.dataset_hash,
            row_count=int(row.row_count),
            event_time_min=row.event_time_min,
            event_time_max=row.event_time_max,
            available_time_max=row.available_time_max,
            sealed_at=row.sealed_at,
            partitions=partitions,
        )

    def latest_sealed(self, dataset_id: str) -> DatasetVersion | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(dataset_versions_table.c.version)
                .where(
                    dataset_versions_table.c.dataset_id == dataset_id,
                    dataset_versions_table.c.state == DatasetState.SEALED.value,
                )
                .order_by(dataset_versions_table.c.version.desc())
                .limit(1)
            ).first()
        if row is None:
            return None
        return self.get_dataset(dataset_id, int(row.version))
