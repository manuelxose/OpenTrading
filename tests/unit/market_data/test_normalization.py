"""Unit tests: instrument + timezone normalization."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from adapters.market_data.errors import (
    InstrumentResolutionError,
    NormalizationError,
    TimestampNormalizationError,
)
from adapters.market_data.normalization import (
    BarPayloadMapper,
    SymbolNormalizer,
    normalize_timestamp,
    parse_timeframe,
)
from core.domain.enums import Timeframe


class TestSymbolNormalizer:
    def test_derives_canonical_form(self) -> None:
        assert SymbolNormalizer.derive("eur/usd") == "EURUSD"
        assert SymbolNormalizer.derive("  eur-usd ") == "EURUSD"
        assert SymbolNormalizer.derive("XAUUSD") == "XAUUSD"

    def test_empty_symbol_rejected(self) -> None:
        with pytest.raises(InstrumentResolutionError):
            SymbolNormalizer.derive("///")

    def test_registry_takes_precedence(self) -> None:
        normalizer = SymbolNormalizer({"eurusd": "EURUSD.FX", "XAUUSD": "GOLD"})
        assert normalizer.normalize("EUR/USD") == "EURUSD.FX"
        assert normalizer.normalize("xauusd") == "GOLD"
        assert normalizer.normalize("US500") == "US500"

    def test_exact_match_beats_normalized_match(self) -> None:
        normalizer = SymbolNormalizer({"eurusd": "NORM", "EUR/USD": "EXACT"})
        assert normalizer.normalize("EUR/USD") == "EXACT"


class TestNormalizeTimestamp:
    def test_aware_datetime_to_utc(self) -> None:
        eastern = datetime(2026, 1, 5, 5, 0, tzinfo=UTC)
        assert normalize_timestamp(eastern) == datetime(2026, 1, 5, 5, 0, tzinfo=UTC)

    def test_naive_defaults_to_utc(self) -> None:
        result = normalize_timestamp(datetime(2026, 1, 5, 10, 0))
        assert result == datetime(2026, 1, 5, 10, 0, tzinfo=UTC)

    def test_naive_with_declared_timezone(self) -> None:
        result = normalize_timestamp(datetime(2026, 1, 5, 11, 0), declared_timezone="Europe/Madrid")
        assert result == datetime(2026, 1, 5, 10, 0, tzinfo=UTC)  # CET winter

    def test_iso_string_with_offset(self) -> None:
        assert normalize_timestamp("2026-01-05T10:00:00+02:00") == datetime(
            2026, 1, 5, 8, 0, tzinfo=UTC
        )

    def test_iso_string_with_z(self) -> None:
        expected = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
        assert normalize_timestamp("2026-01-05T10:00:00Z") == expected

    def test_epoch_seconds_and_milliseconds(self) -> None:
        # 2026-01-05T10:00:00Z == 1767607200 seconds since epoch.
        assert normalize_timestamp(1_767_607_200) == datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
        assert normalize_timestamp(1_767_607_200_000) == datetime(2026, 1, 5, 10, 0, tzinfo=UTC)

    def test_garbage_rejected(self) -> None:
        with pytest.raises(TimestampNormalizationError):
            normalize_timestamp("not-a-time")

    def test_unknown_timezone_rejected(self) -> None:
        with pytest.raises(TimestampNormalizationError):
            normalize_timestamp(datetime(2026, 1, 5), declared_timezone="Mars/Olympus")


class TestParseTimeframe:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("M1", Timeframe.M1), ("1m", Timeframe.M1), ("4h", Timeframe.H4), ("D1", Timeframe.D1)],
    )
    def test_parses(self, raw: str, expected: Timeframe) -> None:
        assert parse_timeframe(raw) is expected

    def test_unknown_returns_none(self) -> None:
        assert parse_timeframe("M2") is None
        assert parse_timeframe(None) is None


class TestBarPayloadMapper:
    def test_canonical_keys_win(self) -> None:
        mapper = BarPayloadMapper()
        payload = {"open": "1.1", "o": "9.9"}
        assert mapper.get(payload, "open") == "1.1"

    def test_alias_fallback(self) -> None:
        mapper = BarPayloadMapper()
        assert mapper.get({"o": "1.1"}, "open") == "1.1"
        assert mapper.get({"t": 123}, "event_time") == 123

    def test_missing_field_raises(self) -> None:
        with pytest.raises(NormalizationError):
            BarPayloadMapper().get({"high": "1"}, "open")
