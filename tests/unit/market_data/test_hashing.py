"""Unit tests: deterministic hashing."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from adapters.market_data.hashing import (
    bar_checksum,
    canonical_bar_bytes,
    canonical_decimal,
    canonical_timestamp,
    dataset_hash,
    partition_hash,
    snapshot_data_hash,
)
from adapters.market_data.snapshot import snapshot_from_bar
from core.clock.clocks import VirtualClock
from core.domain.enums import Timeframe

from factories import FIXED_START, make_bar, make_market_snapshot


def test_canonical_decimal_collapses_trailing_zeros() -> None:
    assert canonical_decimal(Decimal("1.10")) == canonical_decimal(Decimal("1.1"))
    assert canonical_decimal(Decimal("1.10")) == "1.1"


def test_canonical_timestamp_microseconds_and_offset() -> None:
    assert canonical_timestamp(FIXED_START) == "2026-01-05T10:00:00.000000+00:00"


def test_bar_checksum_stable_and_content_sensitive() -> None:
    bar = make_bar(FIXED_START)
    assert bar_checksum(bar) == bar_checksum(make_bar(FIXED_START))
    assert bar_checksum(bar) != bar_checksum(make_bar(FIXED_START, close="9.9"))


def test_bar_checksum_ignores_derived_checksum_field() -> None:
    base = make_bar(FIXED_START)
    with_checksum = base.model_copy(update={"checksum": "abc"})
    assert bar_checksum(base) == bar_checksum(with_checksum)


def test_dataset_hash_deterministic_ordering_independent() -> None:
    bars = (
        make_bar(FIXED_START, source_record_id="a"),
        make_bar(FIXED_START + timedelta(minutes=1), source_record_id="b"),
        make_bar(FIXED_START + timedelta(minutes=2), source_record_id="c"),
    )
    shuffled = (bars[2], bars[0], bars[1])
    assert dataset_hash(bars) == dataset_hash(shuffled)
    assert partition_hash(bars) == dataset_hash(bars)


def test_dataset_hash_sensitive_to_any_field() -> None:
    bars = (
        make_bar(FIXED_START, source_record_id="a"),
        make_bar(FIXED_START + timedelta(minutes=1), source_record_id="b"),
    )
    assert dataset_hash(bars) != dataset_hash(
        (bars[0], make_bar(FIXED_START + timedelta(minutes=1), source_record_id="b", volume="999"))
    )


def test_canonical_bar_bytes_layout() -> None:
    bar = make_bar(FIXED_START, timeframe=Timeframe.M1, quality_flags=())
    expected = (
        "EURUSD\x1fM1\x1fOHLCV\x1f2026-01-05T10:00:00.000000+00:00\x1f"
        "2026-01-05T10:00:00.000000+00:00\x1f2026-01-05T10:00:00.000000+00:00\x1f"
        "1.08\x1f1.0801\x1f1.0799\x1f1.08005\x1f1000\x1f"
        f"fixture-feed\x1f{bar.source_record_id}\x1f"
    )
    assert canonical_bar_bytes(bar) == expected.encode("utf-8")


def test_snapshot_data_hash_excludes_provenance_and_produced_at() -> None:
    a = make_market_snapshot(FIXED_START)
    b = a.model_copy(
        update={
            "produced_at": FIXED_START + timedelta(days=1),
            "trace_id": None,
            "provenance": a.provenance.model_copy(update={"producer": "someone-else"}),
        }
    )
    assert snapshot_data_hash(a) == snapshot_data_hash(b)
    c = a.model_copy(update={"bid": a.bid + Decimal("0.00001")})
    assert snapshot_data_hash(a) != snapshot_data_hash(c)


def test_snapshot_hash_matches_between_derivations() -> None:
    bar = make_bar(FIXED_START)
    clock = VirtualClock(FIXED_START)
    snap = snapshot_from_bar(
        bar, as_of=FIXED_START, clock=clock, dataset_id="ohlcv.EURUSD.M1", dataset_version=1
    )
    snap2 = snapshot_from_bar(
        bar,
        as_of=FIXED_START,
        clock=VirtualClock(FIXED_START + timedelta(days=5)),
        dataset_id="ohlcv.EURUSD.M1",
        dataset_version=1,
    )
    assert snapshot_data_hash(snap) == snapshot_data_hash(snap2)
