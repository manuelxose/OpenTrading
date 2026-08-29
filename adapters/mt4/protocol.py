"""MT4 execution protocol wire models (Phase 6, ADR-0020).

The protocol is versioned (``protocol_version`` = ``"1.0"``) and JSON-over-ZeroMQ
on a private network (§34.18, ADR-0016). Every message is a flat JSON object
(UTF-8, single frame) so the MQL4 EA can parse it with a minimal JSON library —
no nested envelope indirection on the wire.

Message families (see ``mt4/protocol/README.md`` for the normative spec):

- commands   Core→MT4 (REQ): submit_order, cancel_order, modify_order,
  reconciliation_request
- replies    MT4→Core (REP): order_ack, order_reject, reconciliation_response
- events     MT4→Core (PUSH): heartbeat, account_snapshot, position_snapshot,
  partial_fill, fill
- market     MT4→Core (PUB): market_quote

Every command carries the full field set frozen in architecture §8:
protocol_version, trace_id, order_intent_id, strategy_id, strategy_version,
timestamp, expires_at, sequence, symbol, side, quantity, order_type, price,
stop_loss, take_profit, max_slippage — plus a checksum.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal, Self
from uuid import UUID

from core.domain.enums import OrderSide, OrderType, TimeInForce
from core.schemas.base import UtcDateTime, ensure_utc
from core.schemas.trading import PositionSnapshot as CanonicalPositionSnapshot
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from adapters.mt4.errors import Mt4ErrorCode, Mt4ProtocolError, ProtocolErrorDetail

__all__ = [
    "MESSAGE_REGISTRY",
    "PROTOCOL_VERSION",
    "AccountSnapshotEvent",
    "CancelOrderCommand",
    "FillEvent",
    "HeartbeatEvent",
    "MarketQuote",
    "ModifyOrderCommand",
    "Mt4MessageType",
    "OrderAck",
    "OrderReject",
    "PartialFillEvent",
    "PositionSnapshotEvent",
    "ReconciliationRequestCommand",
    "ReconciliationResponse",
    "SubmitOrderCommand",
    "WireMessage",
    "command_fingerprint",
    "parse_message",
    "serialize_message",
]

#: Wire protocol version. Bump rules: MINOR adds optional fields/messages
#: (backward compatible); MAJOR changes semantics or removes fields. A MAJOR
#: mismatch between Core and bridge is a hard reject (PROTOCOL_VERSION_MISMATCH).
PROTOCOL_VERSION = "1.0"


class Mt4MessageType(StrEnum):
    SUBMIT_ORDER = "submit_order"
    CANCEL_ORDER = "cancel_order"
    MODIFY_ORDER = "modify_order"
    RECONCILIATION_REQUEST = "reconciliation_request"
    ORDER_ACK = "order_ack"
    ORDER_REJECT = "order_reject"
    RECONCILIATION_RESPONSE = "reconciliation_response"
    HEARTBEAT = "heartbeat"
    ACCOUNT_SNAPSHOT = "account_snapshot"
    POSITION_SNAPSHOT = "position_snapshot"
    PARTIAL_FILL = "partial_fill"
    FILL = "fill"
    MARKET_QUOTE = "market_quote"


class WireMessage(BaseModel):
    """Common frame for every protocol message (flat JSON object)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    protocol_version: str = Field(default=PROTOCOL_VERSION, min_length=1)
    message_type: Mt4MessageType
    message_id: UUID
    trace_id: UUID | None = None
    timestamp: UtcDateTime
    sequence: int = Field(ge=0)
    correlation_id: UUID | None = Field(default=None)
    checksum: str | None = Field(default=None, description="SHA-256 of canonical payload")

    @model_validator(mode="after")
    def _pin_version(self) -> Self:
        if self.protocol_version.split(".")[0] != PROTOCOL_VERSION.split(".")[0]:
            raise ValueError(
                f"protocol version {self.protocol_version!r} is incompatible "
                f"with {PROTOCOL_VERSION!r}"
            )
        return self

    def canonical_json(self, *, exclude: set[str] | None = None) -> str:
        """Deterministic JSON: field order = class definition order, no spaces."""
        dump = self.model_dump(mode="json", exclude=exclude or set())
        return json.dumps(dump, separators=(",", ":"), ensure_ascii=False)

    def with_checksum(self) -> Self:
        """Return a copy carrying the SHA-256 of the canonical (checksum-less) body."""
        return self.model_copy(update={"checksum": self.compute_checksum()})

    def compute_checksum(self) -> str:
        body = self.canonical_json(exclude={"checksum"})
        return hashlib.sha256(body.encode("utf-8")).hexdigest()

    def verify_checksum(self) -> None:
        """Raise CHECKSUM_MISMATCH when the frame was corrupted in transit."""
        if self.checksum is None or self.checksum != self.compute_checksum():
            raise Mt4ProtocolError(
                ProtocolErrorDetail.create(
                    Mt4ErrorCode.CHECKSUM_MISMATCH,
                    "message checksum does not match its content",
                    trace_id=self.trace_id,
                    now=self.timestamp,
                )
            )

    def to_json_bytes(self) -> bytes:
        return self.canonical_json().encode("utf-8")


#: Command fields that participate in the idempotency fingerprint. Deliberately
#: excluded: message_id/timestamp/sequence/correlation_id/checksum/trace_id —
#: a retry after TIMEOUT may legitimately reuse the intent with a fresh frame.
_FINGERPRINT_EXCLUDE: set[str] = {
    "checksum",
    "correlation_id",
    "message_id",
    "sequence",
    "timestamp",
    "trace_id",
}


class CommandMessage(WireMessage):
    """Base for all Core→MT4 commands.

    Architecture §8 freezes the full field set on every command; subclasses
    enforce which fields are mandatory for their type.
    """

    order_intent_id: UUID | None = Field(default=None)
    strategy_id: str = Field(min_length=1)
    strategy_version: str = Field(min_length=1)
    expires_at: UtcDateTime | None = None
    symbol: str | None = Field(default=None, min_length=1)
    side: OrderSide | None = None
    quantity: Decimal | None = Field(default=None, gt=0)
    order_type: OrderType | None = None
    price: Decimal | None = Field(default=None, gt=0)
    stop_loss: Decimal | None = Field(default=None, gt=0)
    take_profit: Decimal | None = Field(default=None, gt=0)
    max_slippage: Decimal = Field(default=Decimal("0"), ge=0)

    def fingerprint(self) -> str:
        """Content hash identifying this command for idempotency/duplicates.

        Identical intent + fields → identical fingerprint, regardless of frame
        timestamps or retry attempts.
        """
        body = self.canonical_json(exclude=_FINGERPRINT_EXCLUDE)
        return hashlib.sha256(body.encode("utf-8")).hexdigest()


class SubmitOrderCommand(CommandMessage):
    message_type: Literal[Mt4MessageType.SUBMIT_ORDER] = Mt4MessageType.SUBMIT_ORDER
    time_in_force: TimeInForce = TimeInForce.GTC

    @model_validator(mode="after")
    def _check_fields(self) -> Self:
        if self.order_intent_id is None:
            raise ValueError("submit_order requires order_intent_id")
        for name, value in (
            ("symbol", self.symbol),
            ("side", self.side),
            ("quantity", self.quantity),
            ("order_type", self.order_type),
            ("expires_at", self.expires_at),
        ):
            if value is None:
                raise ValueError(f"submit_order requires {name}")
        if self.order_type is not OrderType.MARKET and self.price is None:
            raise ValueError("LIMIT/STOP/STOP_LIMIT orders require a price")
        if self.expires_at is not None and self.expires_at <= self.timestamp:
            raise ValueError("expires_at must be strictly after timestamp")
        return self


class CancelOrderCommand(CommandMessage):
    message_type: Literal[Mt4MessageType.CANCEL_ORDER] = Mt4MessageType.CANCEL_ORDER
    reason: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _check_fields(self) -> Self:
        for name, value in (
            ("order_intent_id", self.order_intent_id),
            ("symbol", self.symbol),
            ("side", self.side),
            ("quantity", self.quantity),
            ("order_type", self.order_type),
            ("expires_at", self.expires_at),
        ):
            if value is None:
                raise ValueError(f"cancel_order requires {name}")
        if self.expires_at is not None and self.expires_at <= self.timestamp:
            raise ValueError("expires_at must be strictly after timestamp")
        return self


class ModifyOrderCommand(CommandMessage):
    message_type: Literal[Mt4MessageType.MODIFY_ORDER] = Mt4MessageType.MODIFY_ORDER
    new_price: Decimal | None = Field(default=None, gt=0)
    new_stop_loss: Decimal | None = Field(default=None, gt=0)
    new_take_profit: Decimal | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _check_fields(self) -> Self:
        for name, value in (
            ("order_intent_id", self.order_intent_id),
            ("symbol", self.symbol),
            ("side", self.side),
            ("quantity", self.quantity),
            ("order_type", self.order_type),
            ("expires_at", self.expires_at),
        ):
            if value is None:
                raise ValueError(f"modify_order requires {name}")
        if not (self.new_price or self.new_stop_loss or self.new_take_profit):
            raise ValueError("modify_order requires at least one new_* value")
        if self.expires_at is not None and self.expires_at <= self.timestamp:
            raise ValueError("expires_at must be strictly after timestamp")
        return self


class ReconciliationRequestCommand(CommandMessage):
    """Global account reconciliation. ``strategy_id`` is the sequence namespace
    (conventionally ``CORE``); ``order_intent_id`` and order fields are null."""

    message_type: Literal[Mt4MessageType.RECONCILIATION_REQUEST] = (
        Mt4MessageType.RECONCILIATION_REQUEST
    )
    scope: Literal["ALL"] = "ALL"


class OrderAck(WireMessage):
    """MT4 accepted a command. ``duplicate`` marks a replay from the idempotency
    ledger (the original outcome already stands)."""

    message_type: Literal[Mt4MessageType.ORDER_ACK] = Mt4MessageType.ORDER_ACK
    order_intent_id: UUID
    status: Literal["SUBMITTED", "ACKNOWLEDGED", "CANCELLED", "FILLED", "MODIFIED"]
    venue_order_id: str | None = Field(default=None, min_length=1)
    duplicate: bool = False
    message: str | None = Field(default=None, max_length=200)


class OrderReject(WireMessage):
    message_type: Literal[Mt4MessageType.ORDER_REJECT] = Mt4MessageType.ORDER_REJECT
    order_intent_id: UUID | None = None
    error: ProtocolErrorDetail


class AccountState(BaseModel):
    """Balance snapshot payload shared by account_snapshot and reconciliation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    account_id: str = Field(min_length=1)
    is_demo: bool = False
    currency: str = Field(min_length=3, max_length=3)
    balance: Decimal
    equity: Decimal
    margin: Decimal = Field(ge=0)
    free_margin: Decimal
    as_of: UtcDateTime


class VenuePosition(BaseModel):
    """One broker-side position (mirrors the canonical PositionSnapshot)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    venue_position_id: str = Field(min_length=1)
    magic: int = Field(ge=0)
    position: CanonicalPositionSnapshot


class ReconciliationResponse(WireMessage):
    message_type: Literal[Mt4MessageType.RECONCILIATION_RESPONSE] = (
        Mt4MessageType.RECONCILIATION_RESPONSE
    )
    account: AccountState
    positions: tuple[VenuePosition, ...] = ()
    open_order_intent_ids: tuple[UUID, ...] = ()
    #: Per-strategy last-accepted command sequences — the Core resyncs its
    #: per-strategy counters to these after a restart (INV-6, §9).
    last_sequences: dict[str, int] = Field(default_factory=dict)
    broker_connected: bool = True
    trading_enabled: bool = True


class HeartbeatEvent(WireMessage):
    message_type: Literal[Mt4MessageType.HEARTBEAT] = Mt4MessageType.HEARTBEAT
    broker_connected: bool = True
    trading_enabled: bool = True
    mode: Literal["PAPER", "LIVE_GATED", "LIVE_AUTO"] = "PAPER"


class AccountSnapshotEvent(WireMessage):
    message_type: Literal[Mt4MessageType.ACCOUNT_SNAPSHOT] = Mt4MessageType.ACCOUNT_SNAPSHOT
    account: AccountState


class PositionSnapshotEvent(WireMessage):
    message_type: Literal[Mt4MessageType.POSITION_SNAPSHOT] = Mt4MessageType.POSITION_SNAPSHOT
    account_id: str = Field(min_length=1)
    positions: tuple[VenuePosition, ...] = ()


class PartialFillEvent(WireMessage):
    message_type: Literal[Mt4MessageType.PARTIAL_FILL] = Mt4MessageType.PARTIAL_FILL
    order_intent_id: UUID
    venue_order_id: str = Field(min_length=1)
    filled_quantity: Decimal = Field(gt=0)
    remaining_quantity: Decimal = Field(ge=0)
    average_fill_price: Decimal = Field(gt=0)
    commission: Decimal = Field(default=Decimal("0"), ge=0)
    slippage: Decimal | None = None
    symbol: str = Field(min_length=1)


class FillEvent(WireMessage):
    message_type: Literal[Mt4MessageType.FILL] = Mt4MessageType.FILL
    order_intent_id: UUID
    venue_order_id: str = Field(min_length=1)
    filled_quantity: Decimal = Field(gt=0)
    average_fill_price: Decimal = Field(gt=0)
    commission: Decimal = Field(default=Decimal("0"), ge=0)
    slippage: Decimal | None = None
    symbol: str = Field(min_length=1)
    side: OrderSide


class MarketQuote(WireMessage):
    message_type: Literal[Mt4MessageType.MARKET_QUOTE] = Mt4MessageType.MARKET_QUOTE
    symbol: str = Field(min_length=1)
    bid: Decimal = Field(gt=0)
    ask: Decimal = Field(gt=0)
    spread: Decimal = Field(ge=0)
    tradable: bool = True

    @model_validator(mode="after")
    def _check_book(self) -> Self:
        if self.ask < self.bid:
            raise ValueError("ask must be >= bid")
        return self


MESSAGE_REGISTRY: dict[Mt4MessageType, type[WireMessage]] = {
    Mt4MessageType.SUBMIT_ORDER: SubmitOrderCommand,
    Mt4MessageType.CANCEL_ORDER: CancelOrderCommand,
    Mt4MessageType.MODIFY_ORDER: ModifyOrderCommand,
    Mt4MessageType.RECONCILIATION_REQUEST: ReconciliationRequestCommand,
    Mt4MessageType.ORDER_ACK: OrderAck,
    Mt4MessageType.ORDER_REJECT: OrderReject,
    Mt4MessageType.RECONCILIATION_RESPONSE: ReconciliationResponse,
    Mt4MessageType.HEARTBEAT: HeartbeatEvent,
    Mt4MessageType.ACCOUNT_SNAPSHOT: AccountSnapshotEvent,
    Mt4MessageType.POSITION_SNAPSHOT: PositionSnapshotEvent,
    Mt4MessageType.PARTIAL_FILL: PartialFillEvent,
    Mt4MessageType.FILL: FillEvent,
    Mt4MessageType.MARKET_QUOTE: MarketQuote,
}


def serialize_message(message: WireMessage) -> bytes:
    """Serialize with an attached checksum (transport integrity, §8)."""
    return message.with_checksum().to_json_bytes()


def parse_message(raw: bytes, *, now: datetime | None = None) -> WireMessage:
    """Parse one frame into a validated wire message (schema validation gate)."""
    now = ensure_utc(now or datetime.now(UTC))
    try:
        data: dict[str, Any] = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise Mt4ProtocolError(
            ProtocolErrorDetail.create(
                Mt4ErrorCode.SCHEMA_INVALID,
                "frame is not a valid protocol message",
                detail=str(exc),
                now=now,
            )
        ) from exc
    raw_type = data.get("message_type")
    if not isinstance(raw_type, str):
        raise Mt4ProtocolError(
            ProtocolErrorDetail.create(
                Mt4ErrorCode.SCHEMA_INVALID,
                "message_type is missing or not a string",
                now=now,
            )
        )
    try:
        message_type = Mt4MessageType(raw_type)
    except ValueError as exc:
        raise Mt4ProtocolError(
            ProtocolErrorDetail.create(
                Mt4ErrorCode.UNKNOWN_MESSAGE_TYPE,
                f"unknown message_type {raw_type!r}",
                detail=str(raw_type),
                now=now,
            )
        ) from exc
    schema_cls = MESSAGE_REGISTRY.get(message_type)
    if schema_cls is None:
        raise Mt4ProtocolError(
            ProtocolErrorDetail.create(
                Mt4ErrorCode.UNKNOWN_MESSAGE_TYPE,
                f"message_type {message_type.value!r} has no schema",
                now=now,
            )
        )
    try:
        return schema_cls.model_validate(data)
    except ValidationError as exc:
        raise Mt4ProtocolError(
            ProtocolErrorDetail.create(
                Mt4ErrorCode.SCHEMA_INVALID,
                f"{message_type.value} failed schema validation",
                detail=str(exc.errors(include_url=False)),
                now=now,
            )
        ) from exc


def command_fingerprint(command: CommandMessage) -> str:
    """Idempotency key content hash for a command frame (see CommandMessage)."""
    return command.fingerprint()
