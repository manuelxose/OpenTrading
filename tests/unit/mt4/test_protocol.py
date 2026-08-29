"""Wire model tests: schema validation, framing, checksum, fingerprints."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from adapters.mt4.errors import Mt4ErrorCode, Mt4ProtocolError
from adapters.mt4.protocol import (
    PROTOCOL_VERSION,
    FillEvent,
    OrderAck,
    SubmitOrderCommand,
    parse_message,
    serialize_message,
)
from core.domain.enums import OrderSide, OrderType
from pydantic import ValidationError
from tests.unit.mt4.helpers import T0, make_submit


def test_protocol_version_is_pinned() -> None:
    assert PROTOCOL_VERSION == "1.0"


def test_submit_requires_command_field_set() -> None:
    with pytest.raises(ValidationError):
        make_submit(symbol=None)  # type: ignore[arg-type]


def test_market_order_needs_no_price_but_limit_does() -> None:
    make_submit(order_type=OrderType.MARKET)
    with pytest.raises(ValidationError):
        make_submit(order_type=OrderType.LIMIT)


def test_side_must_be_buy_or_sell() -> None:
    with pytest.raises(ValidationError):
        make_submit(side="FLAT")  # type: ignore[arg-type]


def test_expires_at_must_follow_timestamp() -> None:
    with pytest.raises(ValidationError):
        make_submit(timestamp=T0, expires_in_seconds=-10)


def test_roundtrip_and_checksum() -> None:
    command = make_submit()
    raw = serialize_message(command)
    parsed = parse_message(raw)
    assert parsed == command.model_copy(update={"checksum": command.compute_checksum()})
    parsed.verify_checksum()  # must not raise


def test_tampered_frame_fails_checksum() -> None:
    command = make_submit()
    parsed = parse_message(serialize_message(command))
    corrupted = parsed.model_copy(update={"checksum": "deadbeef"})
    with pytest.raises(Mt4ProtocolError) as exc:
        corrupted.verify_checksum()
    assert exc.value.code is Mt4ErrorCode.CHECKSUM_MISMATCH


def test_unknown_message_type_rejected() -> None:
    with pytest.raises(Mt4ProtocolError) as exc:
        parse_message(b'{"message_type": "fly_to_moon"}')
    assert exc.value.code is Mt4ErrorCode.UNKNOWN_MESSAGE_TYPE


def test_malformed_json_rejected() -> None:
    with pytest.raises(Mt4ProtocolError) as exc:
        parse_message(b"not-json{")
    assert exc.value.code is Mt4ErrorCode.SCHEMA_INVALID


def test_incompatible_major_version_rejected() -> None:
    data = make_submit().model_dump(mode="python")
    data["protocol_version"] = "2.0"
    with pytest.raises(ValidationError):
        SubmitOrderCommand.model_validate(data)


def test_fingerprint_ignores_frame_fields() -> None:
    """Retries with fresh frames share the fingerprint; field changes do not."""
    first = make_submit()
    retry = first.model_copy(update={"message_id": uuid4(), "timestamp": T0 + timedelta(seconds=1)})
    assert first.fingerprint() == retry.fingerprint()
    changed = first.model_copy(update={"quantity": Decimal("0.20")})
    assert first.fingerprint() != changed.fingerprint()


def test_fill_event_roundtrip() -> None:
    fill = FillEvent(
        message_id=uuid4(),
        timestamp=T0,
        sequence=3,
        order_intent_id=uuid4(),
        venue_order_id="vo-1",
        filled_quantity=Decimal("0.1"),
        average_fill_price=Decimal("1.08"),
        symbol="EURUSD",
        side=OrderSide.BUY,
    )
    parsed = parse_message(serialize_message(fill))
    assert isinstance(parsed, FillEvent)
    assert parsed.filled_quantity == Decimal("0.1")


def test_order_ack_status_enum() -> None:
    with pytest.raises(ValidationError):
        OrderAck(
            message_id=uuid4(),
            timestamp=T0,
            sequence=1,
            order_intent_id=uuid4(),
            status="PENDING_FOREVER",  # type: ignore[arg-type]
        )
