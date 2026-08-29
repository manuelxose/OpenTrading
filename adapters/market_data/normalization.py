"""Instrument and timezone normalization (bronze layer, architecture §13).

- :class:`SymbolNormalizer` — canonical instrument id from arbitrary source
  symbols, with an optional registered-symbol table consulted first.
- :func:`normalize_timestamp` — any timestamp representation into
  timezone-aware UTC; naive timestamps are localized with a declared timezone
  (default UTC, documented and explicit) rather than silently guessed.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from core.domain.enums import Timeframe
from core.schemas.base import ensure_utc
from core.schemas.market_data import Bar

from adapters.market_data.errors import (
    InstrumentResolutionError,
    NormalizationError,
    TimestampNormalizationError,
)

__all__ = ["SymbolNormalizer", "normalize_timestamp", "parse_timeframe"]

#: Source characters removed when deriving a canonical symbol
#: (``EUR/USD`` → ``EURUSD``, ``EUR-USD`` → ``EURUSD``).
_SYMBOL_SEPARATORS = re.compile(r"[/\-_\s]+")


class SymbolNormalizer:
    """Deterministic symbol → instrument_id normalization.

    Resolution order:

    1. exact match in the registered table (PostgreSQL ``instruments``);
    2. normalized-form match in the registered table;
    3. derived canonical form (uppercase, separators removed).

    Unresolvable to *any* instrument id is impossible: the derived form is a
    valid fallback, so ``InstrumentResolutionError`` is only raised by callers
    that require a registered instrument.
    """

    def __init__(self, registry: Mapping[str, str] | None = None) -> None:
        self._registry: dict[str, str] = dict(registry or {})
        # Normalized-form index: lookup by derived canonical form so that
        # lowercase or separated registrations still match source symbols.
        self._normalized_registry: dict[str, str] = {
            self.derive(key): value for key, value in self._registry.items()
        }

    @staticmethod
    def derive(symbol: str) -> str:
        """Canonical form: strip, uppercase, drop separators."""
        compact = _SYMBOL_SEPARATORS.sub("", symbol.strip()).upper()
        if not compact:
            raise InstrumentResolutionError(f"symbol {symbol!r} is empty after normalization")
        return compact

    def normalize(self, symbol: str) -> str:
        if symbol in self._registry:
            return self._registry[symbol]
        derived = self.derive(symbol)
        if derived in self._normalized_registry:
            return self._normalized_registry[derived]
        return derived


def normalize_timestamp(
    value: datetime | str | int | float,
    *,
    declared_timezone: str | None = None,
) -> datetime:
    """Convert any accepted timestamp representation to timezone-aware UTC.

    - aware ``datetime`` → UTC;
    - naive ``datetime`` → localized with ``declared_timezone`` (default UTC);
    - ``str`` → ISO-8601 (with or without offset), else numeric epoch;
    - ``int``/``float`` → epoch seconds (≤ 10^12) or milliseconds (> 10^12).

    The UTC default for naive values is an explicit, documented convention of
    this pipeline (raw feeds that omit timezones are treated as UTC); a source
    that declares a timezone always wins.
    """
    tz: timezone | ZoneInfo | None = None
    if declared_timezone:
        upper = declared_timezone.upper()
        if upper in {"UTC", "Z", "GMT"}:
            tz = UTC
        else:
            try:
                tz = ZoneInfo(declared_timezone)
            except Exception as exc:
                raise TimestampNormalizationError(
                    f"unknown declared timezone {declared_timezone!r}"
                ) from exc

    if isinstance(value, datetime):
        if value.tzinfo is not None and value.utcoffset() is not None:
            return ensure_utc(value)
        # Naive datetime: localize with the declared timezone (UTC by default).
        return ensure_utc(value.replace(tzinfo=tz or UTC))

    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            try:
                return _epoch_to_utc(float(text))
            except ValueError:
                raise TimestampNormalizationError(f"unparseable timestamp {value!r}") from exc
        return normalize_timestamp(parsed, declared_timezone=declared_timezone)

    if isinstance(value, (int, float)):
        return _epoch_to_utc(value)

    raise TimestampNormalizationError(f"unsupported timestamp type {type(value).__name__}")


def _epoch_to_utc(value: int | float) -> datetime:
    seconds = value / 1000.0 if abs(value) > 1e12 else value
    return datetime.fromtimestamp(seconds, tz=UTC)


def parse_timeframe(raw: Any) -> Timeframe | None:
    """Best-effort timeframe parse; ``None`` when absent or unknown."""
    if raw is None:
        return None
    text = str(raw).strip().upper()
    # Accept common source spellings: "1m" → M1, "4h" → H4, …
    aliases = {"1M": "M1", "5M": "M5", "15M": "M15", "30M": "M30", "1H": "H1", "4H": "H4"}
    resolved = aliases.get(text, text)
    try:
        return Timeframe(resolved)
    except ValueError:
        return None


#: Source payload key aliases → canonical bar field names (deterministic).
_BAR_FIELD_ALIASES: dict[str, str] = {
    "o": "open",
    "h": "high",
    "l": "low",
    "c": "close",
    "v": "volume",
    "t": "event_time",
    "time": "event_time",
    "open_time": "event_time",
    "timestamp": "event_time",
    "dt": "event_time",
    "instrument": "symbol",
    "ticker": "symbol",
}


class BarPayloadMapper:
    """Deterministic OHLCV mapping from raw source payloads.

    Canonical keys win; a fixed alias table handles the most common broker/
    feed spellings. Unknown keys are ignored (closed-by-construction).
    """

    def get(self, payload: Mapping[str, Any], field: str) -> Any:
        if field in payload:
            return payload[field]
        for alias, canonical in _BAR_FIELD_ALIASES.items():
            if canonical == field and alias in payload:
                return payload[alias]
        raise NormalizationError(f"payload is missing required field {field!r}")


def build_bar_from_payload(
    payload: Mapping[str, Any],
    *,
    source: str,
    source_record_id: str,
    available_time: datetime,
    ingested_at: datetime,
    instrument_id: str,
    timeframe: Timeframe,
    event_time: datetime | None = None,
) -> Bar:
    """Assemble a normalized Bar from a mapped raw payload (bronze)."""
    mapper = BarPayloadMapper()

    def price(field: str) -> Decimal:
        raw = mapper.get(payload, field)
        try:
            return Decimal(str(raw))
        except (InvalidOperation, ValueError):
            raise NormalizationError(f"field {field!r} is not numeric: {raw!r}") from None

    event = (
        normalize_timestamp(event_time)
        if event_time is not None
        else normalize_timestamp(mapper.get(payload, "event_time"))
    )
    return Bar(
        instrument_id=instrument_id,
        timeframe=timeframe,
        event_time=event,
        available_time=available_time,
        ingested_at=ingested_at,
        open=price("open"),
        high=price("high"),
        low=price("low"),
        close=price("close"),
        volume=price("volume"),
        source=source,
        source_record_id=source_record_id,
    )
