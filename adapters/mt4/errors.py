"""Structured error codes for the MT4 execution protocol (Phase 6, ADR-0020).

Every failure crossing the wire between Core and the MT4 bridge carries a
machine-readable ``Mt4ErrorCode`` — never a free-text-only rejection. Codes are
grouped by the layer that produced them so both sides (Python core, MQL4 EA)
share one vocabulary.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from core.schemas.base import ensure_utc
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "MT4_ERROR_CODE_VERSION",
    "Mt4ErrorCode",
    "Mt4ProtocolError",
    "ProtocolErrorDetail",
    "is_retryable",
]

#: Error-code vocabulary version, independent from the wire protocol version.
MT4_ERROR_CODE_VERSION = "1.0"


class Mt4ErrorCode(StrEnum):
    """Canonical rejection vocabulary for the MT4 bridge (ADR-0020).

    Layers: transport / protocol / validation / venue. The MQL4 EA and the
    Python emulator must emit identical codes for identical conditions so the
    Core can handle both without venue-specific branches.
    """

    # ── Transport & connection ────────────────────────────────────────────
    NOT_CONNECTED = "NOT_CONNECTED"
    TIMEOUT = "TIMEOUT"
    CONNECTION_LOST = "CONNECTION_LOST"

    # ── Protocol framing ──────────────────────────────────────────────────
    SCHEMA_INVALID = "SCHEMA_INVALID"
    CHECKSUM_MISMATCH = "CHECKSUM_MISMATCH"
    PROTOCOL_VERSION_MISMATCH = "PROTOCOL_VERSION_MISMATCH"
    UNKNOWN_MESSAGE_TYPE = "UNKNOWN_MESSAGE_TYPE"

    # ── Ordering guarantees ───────────────────────────────────────────────
    SEQUENCE_VIOLATION = "SEQUENCE_VIOLATION"
    COMMAND_EXPIRED = "COMMAND_EXPIRED"
    DUPLICATE_INTENT = "DUPLICATE_INTENT"
    INTENT_CONFLICT = "INTENT_CONFLICT"
    UNKNOWN_ORDER = "UNKNOWN_ORDER"
    ORDER_NOT_ACTIVE = "ORDER_NOT_ACTIVE"
    INVALID_MODIFICATION = "INVALID_MODIFICATION"

    # ── Venue / broker-side validation (defense-in-depth, INV-5) ─────────
    TRADING_DISABLED = "TRADING_DISABLED"
    SAFE_MODE_ACTIVE = "SAFE_MODE_ACTIVE"
    BROKER_DISCONNECTED = "BROKER_DISCONNECTED"
    SYMBOL_NOT_ALLOWED = "SYMBOL_NOT_ALLOWED"
    LOT_STEP_INVALID = "LOT_STEP_INVALID"
    LOT_LIMIT_EXCEEDED = "LOT_LIMIT_EXCEEDED"
    INSUFFICIENT_MARGIN = "INSUFFICIENT_MARGIN"
    SPREAD_TOO_HIGH = "SPREAD_TOO_HIGH"
    STALE_QUOTES = "STALE_QUOTES"
    MARKET_CLOSED = "MARKET_CLOSED"
    STOP_LEVEL_VIOLATION = "STOP_LEVEL_VIOLATION"
    INVALID_MAGIC = "INVALID_MAGIC"
    SLIPPAGE_CAP_EXCEEDED = "SLIPPAGE_CAP_EXCEEDED"

    # ── Broker / emulator internals ───────────────────────────────────────
    BROKER_ERROR = "BROKER_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


#: Codes a sender may retry safely. Idempotency keys make retries harmless:
#: the receiver re-acks the original outcome instead of executing twice.
_RETRYABLE: frozenset[Mt4ErrorCode] = frozenset(
    {
        Mt4ErrorCode.TIMEOUT,
        Mt4ErrorCode.CONNECTION_LOST,
        Mt4ErrorCode.BROKER_DISCONNECTED,
        Mt4ErrorCode.INTERNAL_ERROR,
    }
)


def is_retryable(code: Mt4ErrorCode) -> bool:
    """True when retrying the identical command is safe and meaningful."""
    return code in _RETRYABLE


class ProtocolErrorDetail(BaseModel):
    """Machine-readable rejection carried by ``order_reject`` messages."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: Mt4ErrorCode
    message: str = Field(min_length=1)
    detail: str | None = None
    trace_id: UUID | None = None
    order_intent_id: UUID | None = None
    symbol: str | None = None
    sequence: int | None = Field(default=None, ge=0)
    produced_at: datetime

    @classmethod
    def create(
        cls,
        code: Mt4ErrorCode,
        message: str,
        *,
        detail: str | None = None,
        trace_id: UUID | None = None,
        order_intent_id: UUID | None = None,
        symbol: str | None = None,
        sequence: int | None = None,
        now: datetime,
    ) -> ProtocolErrorDetail:
        return cls(
            code=code,
            message=message,
            detail=detail,
            trace_id=trace_id,
            order_intent_id=order_intent_id,
            symbol=symbol,
            sequence=sequence,
            produced_at=ensure_utc(now),
        )


class Mt4ProtocolError(Exception):
    """A structured MT4-protocol failure raised inside the Python Core.

    Carries the same :class:`ProtocolErrorDetail` that a remote rejection
    would deliver over the wire, so local and remote failures are handled
    through one path.
    """

    def __init__(self, detail: ProtocolErrorDetail) -> None:
        self.detail = detail
        super().__init__(f"{detail.code.value}: {detail.message}")

    @property
    def code(self) -> Mt4ErrorCode:
        return self.detail.code

    @property
    def is_retryable(self) -> bool:
        return is_retryable(self.code)
