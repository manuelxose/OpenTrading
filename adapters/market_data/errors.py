"""Market data platform errors.

Concrete error types so callers (pipeline, repository, API) can distinguish
"no data", "not sealed yet", "tamper attempt" and "leakage attempt" without
string matching.
"""

from __future__ import annotations


class MarketDataError(Exception):
    """Base class for every market data platform error."""


class InstrumentResolutionError(MarketDataError):
    """A source symbol could not be resolved to a canonical instrument id."""


class NormalizationError(MarketDataError):
    """A raw payload could not be mapped to a normalized record."""


class TimestampNormalizationError(MarketDataError):
    """A source timestamp could not be converted to timezone-aware UTC."""


class DatasetNotFoundError(MarketDataError):
    """The requested dataset version does not exist."""


class DatasetVersionExistsError(MarketDataError):
    """A dataset version with the same (dataset_id, version) already exists."""


class DatasetNotSealedError(MarketDataError):
    """The dataset exists but is still OPEN; only SEALED versions are readable."""


class DatasetSealedError(MarketDataError):
    """An attempt to mutate an already SEALED (immutable) dataset version."""


class FutureDataLeakageError(MarketDataError):
    """INV-3 violation: a record with available_time/event_time > as_of reached
    the query surface. Raised by defense-in-depth guards, never as the primary
    filter mechanism (that is PointInTimeFilter)."""
