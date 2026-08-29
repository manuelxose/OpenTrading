"""Market data pipeline contracts (Phase 1 — Data Platform, architecture §13).

Medallion flow: ``RawMarketRecord`` (raw) → ``Bar`` (bronze/silver) →
``DatasetVersion`` (gold, sealed + hash). Every record distinguishes the three
temporal coordinates that make point-in-time correctness possible (INV-3):

- ``event_time``      — when the market event happened (bar open time);
- ``available_time``  — when the event became knowable to the platform
  (declared by the source, or conservatively the ingestion instant when the
  source does not declare one — never earlier than reality);
- ``ingested_at``     — pipeline clock instant when the record was ingested.

Absolute invariant (Phase 1 DoD): **no record with ``available_time > as_of``
may appear in a query result or a ``MarketSnapshot``.** The enforcement point is
:class:`adapters.market_data.repository.PointInTimeFilter`, the single choke
point every read path goes through.

These are *data records*, not §15 domain contracts, so they are not listed in
``CANONICAL_CONTRACTS``; they still pin ``schema_version`` like every contract.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, ClassVar, Self
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from core.domain.enums import (
    DataQualityFlag,
    DatasetState,
    IngestionStatus,
    MarketDataClass,
    Timeframe,
)
from core.schemas.base import (
    SCHEMA_VERSION,
    BaseContractModel,
    UtcDateTime,
)

__all__ = [
    "Bar",
    "BarGap",
    "DataRecord",
    "DatasetPartition",
    "DatasetVersion",
    "IngestionRun",
    "RawMarketRecord",
]


class DataRecord(BaseContractModel):
    """Base for medallion pipeline records (immutable, closed, version-pinned)."""

    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION

    schema_version: str = Field(
        default=SCHEMA_VERSION,
        description="Schema version of this record. Pinned to the class constant.",
    )

    @model_validator(mode="after")
    def _pin_schema_version(self) -> Self:
        if self.schema_version != self.SCHEMA_VERSION:
            raise ValueError(
                f"{type(self).__name__} requires schema_version "
                f"{self.SCHEMA_VERSION!r}, got {self.schema_version!r}"
            )
        return self

    def canonical_dict(self) -> dict[str, Any]:
        """JSON-mode mapping (UUIDs/Decimals/datetimes as str) for APIs."""
        return self.model_dump(mode="json")


class RawMarketRecord(DataRecord):
    """Verbatim source record plus its ingestion envelope (RAW layer).

    ``payload`` is stored exactly as the source produced it; nothing is
    transformed here, so provenance is never lost and the pipeline can be
    replayed deterministically from the raw layer.
    """

    source: str = Field(min_length=1)
    source_record_id: str = Field(min_length=1)
    data_class: MarketDataClass = MarketDataClass.OHLCV
    event_time: UtcDateTime
    available_time: UtcDateTime | None = Field(
        default=None,
        description=(
            "When the event became knowable. None means the source did not "
            "declare it; bronze infers it as ingested_at (conservative)."
        ),
    )
    ingested_at: UtcDateTime
    payload: dict[str, Any]


class Bar(DataRecord):
    """Normalized OHLCV bar (BRONZE/SILVER layers).

    ``quality_flags`` are attached by the quality engine in silver and never
    mutated afterwards; ``checksum`` is the deterministic row hash
    (:func:`adapters.market_data.hashing.bar_checksum`).
    """

    instrument_id: str = Field(min_length=1, max_length=32)
    timeframe: Timeframe
    data_class: MarketDataClass = MarketDataClass.OHLCV
    event_time: UtcDateTime
    available_time: UtcDateTime
    ingested_at: UtcDateTime
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    volume: Decimal = Field(ge=0)
    source: str = Field(min_length=1)
    source_record_id: str = Field(min_length=1)
    quality_flags: tuple[DataQualityFlag, ...] = ()
    checksum: str | None = Field(default=None)

    @model_validator(mode="after")
    def _check_low_high(self) -> Self:
        # Structural corruption (low > high) is rejected outright; open/close
        # vs high/low inconsistencies are data anomalies, not schema errors,
        # and are handled as PRICE_ANOMALY flags by the quality engine.
        if self.low > self.high:
            raise ValueError("low must be <= high")
        return self


class BarGap(DataRecord):
    """Detected missing bar in the expected grid (interior gaps only)."""

    instrument_id: str = Field(min_length=1, max_length=32)
    timeframe: Timeframe
    expected_time: UtcDateTime
    previous_time: UtcDateTime
    next_time: UtcDateTime | None = None
    detected_at: UtcDateTime


class DatasetPartition(DataRecord):
    """One deterministic gold Parquet object belonging to a dataset version."""

    object_key: str = Field(min_length=1)
    row_count: int = Field(ge=0)
    checksum: str = Field(min_length=1, description="SHA-256 over the partition rows")


class DatasetVersion(DataRecord):
    """Catalog entry for one immutable gold dataset version.

    The DoD anchor: ``(instrument_id, dataset_version, as_of)`` always yields
    the exact same snapshot hash because a SEALED version is immutable and its
    ``dataset_hash`` covers the complete, deterministically ordered content.
    """

    dataset_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    instrument_id: str = Field(min_length=1, max_length=32)
    data_class: MarketDataClass = MarketDataClass.OHLCV
    timeframe: Timeframe
    state: DatasetState = DatasetState.OPEN
    dataset_hash: str | None = None
    row_count: int = Field(default=0, ge=0)
    event_time_min: UtcDateTime | None = None
    event_time_max: UtcDateTime | None = None
    available_time_max: UtcDateTime | None = None
    sealed_at: UtcDateTime | None = None
    partitions: tuple[DatasetPartition, ...] = ()

    @model_validator(mode="after")
    def _check_sealed_state(self) -> Self:
        if self.state is DatasetState.SEALED:
            if not self.dataset_hash or self.sealed_at is None:
                raise ValueError("SEALED dataset version requires dataset_hash and sealed_at")
        elif self.dataset_hash is not None:
            raise ValueError("OPEN dataset version must not carry a dataset_hash")
        return self


class IngestionRun(DataRecord):
    """State of one raw→bronze→silver ingestion run (PostgreSQL catalog)."""

    run_id: UUID = Field(default_factory=uuid4)
    source: str = Field(min_length=1)
    data_class: MarketDataClass = MarketDataClass.OHLCV
    status: IngestionStatus = IngestionStatus.STARTED
    started_at: UtcDateTime
    finished_at: UtcDateTime | None = None
    stats: dict[str, int] = Field(default_factory=dict)
    gaps: tuple[BarGap, ...] = ()
    error: str | None = None


def dataset_id_for(instrument_id: str, timeframe: Timeframe) -> str:
    """Canonical gold dataset identifier (architecture §13 catalog)."""
    return f"ohlcv.{instrument_id}.{timeframe.value}"
