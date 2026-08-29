"""Envelope construction, serialization and validation (INV-15)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from core.clock.clocks import Clock
from core.events.registry import CANONICAL_EVENT_REGISTRY
from core.events.upgrades import upgrade_payload
from core.schemas.base import DomainObject
from core.schemas.events import DomainEvent

__all__ = ["build_domain_event", "deserialize_event", "serialize_event"]


def build_domain_event(
    *,
    event_name: str,
    payload: DomainObject,
    clock: Clock,
    producer: str,
    trace_id: UUID | None = None,
    event_time: datetime | None = None,
    ingested_at: datetime | None = None,
) -> DomainEvent:
    """Build a standard envelope around a validated canonical payload.

    The payload class must be the registered contract for ``event_name``.
    """
    schema_cls = CANONICAL_EVENT_REGISTRY.payload_schema(event_name)
    if not isinstance(payload, schema_cls):
        raise TypeError(
            f"payload for {event_name!r} must be a {schema_cls.__name__} instance, "
            f"got {type(payload).__name__}"
        )
    if payload.schema_version != schema_cls.SCHEMA_VERSION:
        raise ValueError(
            f"payload schema_version {payload.schema_version!r} does not match "
            f"{schema_cls.SCHEMA_VERSION!r}"
        )
    event_time = event_time or clock.now()
    return DomainEvent(
        event_id=uuid4(),
        trace_id=trace_id,
        event_time=event_time,
        ingested_at=ingested_at or clock.now(),
        producer=producer,
        event_name=event_name,
        payload=payload.canonical_dict(),
        provenance={
            "payload_schema": schema_cls.__name__,
            "payload_schema_version": schema_cls.SCHEMA_VERSION,
        },
    )


def serialize_event(event: DomainEvent) -> bytes:
    """Deterministic UTF-8 bytes for the event bus."""
    return event.model_dump_json().encode("utf-8")


def deserialize_event(raw: str | bytes | dict[str, Any]) -> DomainEvent:
    """Deserialize and fully validate an envelope (including its payload contract).

    Payloads with an older ``schema_version`` are upgraded through the registered
    chain before validation (event versioning).
    """
    if isinstance(raw, dict):
        envelope = DomainEvent.model_validate(raw)
    else:
        envelope = DomainEvent.model_validate_json(raw)

    schema_cls = CANONICAL_EVENT_REGISTRY.payload_schema(envelope.event_name)
    payload_dict = upgrade_payload(envelope.event_name, envelope.payload)
    validated_payload = schema_cls.model_validate(payload_dict)
    return envelope.model_copy(update={"payload": validated_payload.canonical_dict()})
