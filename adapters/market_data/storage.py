"""Medallion object storage (architecture §13, ADR-0011).

- :class:`LayerStore` — protocol every read/write path goes through;
- :class:`MemoryLayerStore` — deterministic in-memory implementation (tests);
- :class:`MinioLayerStore` — S3-compatible Parquet storage, one bucket per layer
  (``raw``/``bronze``/``silver``/``gold``, provisioned by ``minio-init``).

Object keys are deterministic by construction (fixed layout helpers), so the
same input always lands on the same keys — a precondition for reproducible
dataset hashes.
"""

from __future__ import annotations

import io
import json
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any, Protocol, cast

import pyarrow as pa
import pyarrow.parquet as pq
from core.domain.enums import DataQualityFlag, LayerName, MarketDataClass, Timeframe
from core.schemas.market_data import Bar, RawMarketRecord

__all__ = [
    "LayerStore",
    "MemoryLayerStore",
    "MinioLayerStore",
    "bars_to_parquet",
    "gold_part_key",
    "gold_prefix",
    "manifest_key",
    "parquet_to_bars",
    "parquet_to_raw",
    "raw_key",
    "raw_to_parquet",
    "run_bars_key",
]

#: Layer → bucket name (provisioned by infra/compose minio-init).
_BUCKETS: dict[LayerName, str] = {
    LayerName.RAW: "raw",
    LayerName.BRONZE: "bronze",
    LayerName.SILVER: "silver",
    LayerName.GOLD: "gold",
}

#: Decimal quantization scale for Parquet decimal128(38, 8) columns.
_DECIMAL_SCALE = Decimal("0.00000001")


# ── Deterministic object key layout ──────────────────────────────────────────
def raw_key(source: str, data_class: MarketDataClass, run_id: str) -> str:
    return f"{source}/{data_class.value}/runs/{run_id}/records.parquet"


def run_bars_key(
    data_class: MarketDataClass,
    instrument_id: str,
    timeframe: Timeframe,
    run_id: str,
) -> str:
    return f"{data_class.value}/{instrument_id}/{timeframe.value}/run={run_id}/part-00000.parquet"


def gold_prefix(
    data_class: MarketDataClass,
    instrument_id: str,
    timeframe: Timeframe,
    version: int,
) -> str:
    return f"{data_class.value}/{instrument_id}/{timeframe.value}/v{version:06d}/"


def gold_part_key(
    data_class: MarketDataClass,
    instrument_id: str,
    timeframe: Timeframe,
    version: int,
    year: int,
    month: int,
    index: int,
) -> str:
    prefix = gold_prefix(data_class, instrument_id, timeframe, version)
    return f"{prefix}year={year}/month={month:02d}/part-{index:05d}.parquet"


def manifest_key(
    data_class: MarketDataClass,
    instrument_id: str,
    timeframe: Timeframe,
    version: int,
) -> str:
    return f"{gold_prefix(data_class, instrument_id, timeframe, version)}_manifest.json"


# ── LayerStore protocol ──────────────────────────────────────────────────────
class LayerStore(Protocol):
    """Read/write interface for the four medallion layers."""

    def write_raw(self, key: str, records: tuple[RawMarketRecord, ...]) -> None: ...

    def read_raw(self, key: str) -> tuple[RawMarketRecord, ...]: ...

    def write_bars(self, layer: LayerName, key: str, bars: tuple[Bar, ...]) -> None: ...

    def read_bars(self, layer: LayerName, key: str) -> tuple[Bar, ...]: ...

    def write_json(self, layer: LayerName, key: str, payload: dict[str, Any]) -> None: ...

    def read_json(self, layer: LayerName, key: str) -> dict[str, Any]: ...

    def list_keys(self, layer: LayerName, prefix: str) -> list[str]: ...


class MemoryLayerStore:
    """Deterministic in-memory store used by unit and leakage tests."""

    def __init__(self) -> None:
        self._objects: dict[tuple[LayerName, str], Any] = {}

    def write_raw(self, key: str, records: tuple[RawMarketRecord, ...]) -> None:
        self._objects[(LayerName.RAW, key)] = tuple(records)

    def read_raw(self, key: str) -> tuple[RawMarketRecord, ...]:
        value = self._objects[(LayerName.RAW, key)]
        return tuple(value)

    def write_bars(self, layer: LayerName, key: str, bars: tuple[Bar, ...]) -> None:
        self._objects[(layer, key)] = tuple(bars)

    def read_bars(self, layer: LayerName, key: str) -> tuple[Bar, ...]:
        value = self._objects[(layer, key)]
        return tuple(value)

    def write_json(self, layer: LayerName, key: str, payload: dict[str, Any]) -> None:
        self._objects[(layer, key)] = json.loads(json.dumps(payload))

    def read_json(self, layer: LayerName, key: str) -> dict[str, Any]:
        value = self._objects[(layer, key)]
        return cast(dict[str, Any], value)

    def list_keys(self, layer: LayerName, prefix: str) -> list[str]:
        return sorted(
            key
            for (layer_name, key) in self._objects
            if layer_name is layer and key.startswith(prefix)
        )


# ── Parquet codecs (unit-testable without MinIO) ─────────────────────────────
BAR_SCHEMA = pa.schema(
    [
        pa.field("instrument_id", pa.string(), nullable=False),
        pa.field("timeframe", pa.string(), nullable=False),
        pa.field("data_class", pa.string(), nullable=False),
        pa.field("event_time", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("available_time", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("ingested_at", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("open", pa.decimal128(38, 8), nullable=False),
        pa.field("high", pa.decimal128(38, 8), nullable=False),
        pa.field("low", pa.decimal128(38, 8), nullable=False),
        pa.field("close", pa.decimal128(38, 8), nullable=False),
        pa.field("volume", pa.decimal128(38, 8), nullable=False),
        pa.field("source", pa.string(), nullable=False),
        pa.field("source_record_id", pa.string(), nullable=False),
        pa.field("quality_flags", pa.list_(pa.string()), nullable=False),
        pa.field("checksum", pa.string(), nullable=True),
    ]
)

RAW_SCHEMA = pa.schema(
    [
        pa.field("source", pa.string(), nullable=False),
        pa.field("source_record_id", pa.string(), nullable=False),
        pa.field("data_class", pa.string(), nullable=False),
        pa.field("event_time", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("available_time", pa.timestamp("us", tz="UTC"), nullable=True),
        pa.field("ingested_at", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("payload", pa.string(), nullable=False),
        pa.field("schema_version", pa.string(), nullable=False),
    ]
)


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(_DECIMAL_SCALE, rounding=ROUND_HALF_EVEN)


def bars_to_parquet(bars: tuple[Bar, ...]) -> bytes:
    """Serialize bars to Parquet bytes (deterministic column order)."""
    rows: list[dict[str, Any]] = []
    for bar in bars:
        rows.append(
            {
                "instrument_id": bar.instrument_id,
                "timeframe": bar.timeframe.value,
                "data_class": bar.data_class.value,
                "event_time": bar.event_time,
                "available_time": bar.available_time,
                "ingested_at": bar.ingested_at,
                "open": _quantize(bar.open),
                "high": _quantize(bar.high),
                "low": _quantize(bar.low),
                "close": _quantize(bar.close),
                "volume": _quantize(bar.volume),
                "source": bar.source,
                "source_record_id": bar.source_record_id,
                "quality_flags": [flag.value for flag in bar.quality_flags],
                "checksum": bar.checksum,
            }
        )
    table = pa.Table.from_pylist(rows, schema=BAR_SCHEMA)
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink)
    return cast(bytes, sink.getvalue().to_pybytes())


def parquet_to_bars(data: bytes) -> tuple[Bar, ...]:
    """Deserialize bars from Parquet bytes."""
    if not data:
        return ()
    table = pq.read_table(pa.BufferReader(data))
    bars: list[Bar] = []
    for row in table.to_pylist():
        row["quality_flags"] = tuple(
            DataQualityFlag(flag) for flag in row.get("quality_flags") or []
        )
        bars.append(Bar(**row))
    return tuple(bars)


def raw_to_parquet(records: tuple[RawMarketRecord, ...]) -> bytes:
    rows: list[dict[str, Any]] = []
    for record in records:
        rows.append(
            {
                "source": record.source,
                "source_record_id": record.source_record_id,
                "data_class": record.data_class.value,
                "event_time": record.event_time,
                "available_time": record.available_time,
                "ingested_at": record.ingested_at,
                "payload": json.dumps(record.payload, sort_keys=True, separators=(",", ":")),
                "schema_version": record.schema_version,
            }
        )
    table = pa.Table.from_pylist(rows, schema=RAW_SCHEMA)
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink)
    return cast(bytes, sink.getvalue().to_pybytes())


def parquet_to_raw(data: bytes) -> tuple[RawMarketRecord, ...]:
    if not data:
        return ()
    table = pq.read_table(pa.BufferReader(data))
    records: list[RawMarketRecord] = []
    for row in table.to_pylist():
        row["payload"] = json.loads(row["payload"])
        records.append(RawMarketRecord(**row))
    return tuple(records)


# ── MinIO implementation ─────────────────────────────────────────────────────
class MinioLayerStore:
    """S3-compatible object storage backed by MinIO (ADR-0011)."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        *,
        secure: bool = False,
    ) -> None:
        from minio import Minio  # local import keeps core import-light

        self._client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )

    def _put_bytes(self, layer: LayerName, key: str, data: bytes) -> None:
        self._client.put_object(
            _BUCKETS[layer],
            key,
            io.BytesIO(data),
            length=len(data),
        )

    def _get_bytes(self, layer: LayerName, key: str) -> bytes:
        response = None
        try:
            response = self._client.get_object(_BUCKETS[layer], key)
            return response.read()
        finally:
            if response is not None:
                response.close()
                response.release_conn()

    def write_raw(self, key: str, records: tuple[RawMarketRecord, ...]) -> None:
        self._put_bytes(LayerName.RAW, key, raw_to_parquet(records))

    def read_raw(self, key: str) -> tuple[RawMarketRecord, ...]:
        return parquet_to_raw(self._get_bytes(LayerName.RAW, key))

    def write_bars(self, layer: LayerName, key: str, bars: tuple[Bar, ...]) -> None:
        self._put_bytes(layer, key, bars_to_parquet(bars))

    def read_bars(self, layer: LayerName, key: str) -> tuple[Bar, ...]:
        return parquet_to_bars(self._get_bytes(layer, key))

    def write_json(self, layer: LayerName, key: str, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self._put_bytes(layer, key, data)

    def read_json(self, layer: LayerName, key: str) -> dict[str, Any]:
        raw = self._get_bytes(layer, key)
        value = json.loads(raw.decode("utf-8"))
        return dict(value)

    def list_keys(self, layer: LayerName, prefix: str) -> list[str]:
        objects = self._client.list_objects(_BUCKETS[layer], prefix=prefix)
        return sorted(obj.object_name for obj in objects)
