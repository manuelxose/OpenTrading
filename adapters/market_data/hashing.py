"""Deterministic hashing for market data (Phase 1 DoD, INV-3).

Three hash families, all SHA-256 over canonical byte encodings:

- :func:`bar_checksum` — per-row content hash;
- :func:`partition_hash` / :func:`dataset_hash` — gold object / dataset hashes;
- :func:`snapshot_data_hash` — hash of the *data* fields of a MarketSnapshot
  (provenance, produced_at and trace_id are excluded so that rebuilding the
  same snapshot from the same sealed dataset always hashes identically).

Canonicalization rules (stable across processes and platforms):

- timestamps: UTC ISO-8601 with microsecond precision and explicit offset;
- decimals: ``str(d.normalize())`` so ``1.10`` and ``1.1`` collide;
- flags: sorted enum values joined by ``|``;
- rows: ordered by ``(event_time, instrument_id, timeframe, source_record_id)``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

from core.domain.enums import Timeframe
from core.schemas.market import MarketSnapshot
from core.schemas.market_data import Bar

#: Field separator inside a canonical row.
_FIELD_SEP = "\x1f"
#: Row separator inside a dataset hash stream.
_ROW_SEP = "\n"


def canonical_timestamp(value: datetime) -> str:
    """UTC ISO-8601 with microsecond precision and explicit ``+00:00``."""
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def canonical_decimal(value: Decimal) -> str:
    """Normalized decimal text: ``1.10`` → ``"1.1"``, ``1E+3`` → ``"1000"``."""
    return format(value.normalize(), "f")


def bar_row_key(bar: Bar) -> tuple[datetime, str, Timeframe, str]:
    """Deterministic ordering key for bars."""
    return (bar.event_time, bar.instrument_id, bar.timeframe, bar.source_record_id)


def canonical_bar_bytes(bar: Bar) -> bytes:
    """Canonical bytes for one bar (checksum excluded: it is derived)."""
    fields = [
        bar.instrument_id,
        bar.timeframe.value,
        bar.data_class.value,
        canonical_timestamp(bar.event_time),
        canonical_timestamp(bar.available_time),
        canonical_timestamp(bar.ingested_at),
        canonical_decimal(bar.open),
        canonical_decimal(bar.high),
        canonical_decimal(bar.low),
        canonical_decimal(bar.close),
        canonical_decimal(bar.volume),
        bar.source,
        bar.source_record_id,
        "|".join(sorted(flag.value for flag in bar.quality_flags)),
    ]
    return _FIELD_SEP.join(fields).encode("utf-8")


def bar_checksum(bar: Bar) -> str:
    """SHA-256 of the canonical bytes of one bar."""
    return hashlib.sha256(canonical_bar_bytes(bar)).hexdigest()


def _hash_stream(bars: Iterable[Bar]) -> Any:
    """Build a SHA-256 digest over rows in deterministic order."""
    digest = hashlib.sha256()
    for bar in sorted(bars, key=bar_row_key):
        digest.update(canonical_bar_bytes(bar))
        digest.update(_ROW_SEP.encode("utf-8"))
    return digest


def partition_hash(bars: Iterable[Bar]) -> str:
    """SHA-256 over one gold partition (rows in deterministic order)."""
    return cast(str, _hash_stream(bars).hexdigest())


def dataset_hash(bars: Iterable[Bar]) -> str:
    """SHA-256 over the complete dataset (rows in deterministic order)."""
    return cast(str, _hash_stream(bars).hexdigest())


#: MarketSnapshot fields that participate in the deterministic snapshot hash.
#: ``produced_at``, ``provenance``, ``trace_id`` and ``schema_version`` are
#: excluded on purpose: they describe the *builder*, not the data.
SNAPSHOT_DATA_FIELDS: tuple[str, ...] = (
    "instrument_id",
    "as_of",
    "source_timestamp",
    "bid",
    "ask",
    "last",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "timeframe",
    "source",
)


def snapshot_data_hash(snapshot: MarketSnapshot) -> str:
    """Deterministic hash of a snapshot's data fields (Phase 1 DoD).

    Given the same ``(instrument_id, dataset_version, as_of)`` the derived
    snapshot data never changes, so this hash is reproducible across runs.
    """
    values: dict[str, object] = {}
    for name in SNAPSHOT_DATA_FIELDS:
        value: object = getattr(snapshot, name)
        if isinstance(value, datetime):
            value = canonical_timestamp(value)
        elif isinstance(value, Decimal):
            value = canonical_decimal(value)
        elif hasattr(value, "value"):  # enums (Timeframe)
            value = value.value
        values[name] = value
    canonical_json = json.dumps(values, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(canonical_json).hexdigest()
