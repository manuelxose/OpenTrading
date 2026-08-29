"""Event emission plumbing for the execution engine (architecture §14).

The Redis Streams bus lands in a later phase (INV-15); until then engines emit
canonical :class:`DomainEvent` envelopes into an :class:`EventSink` — validated
against the canonical payload registry (:mod:`core.events.registry`).
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID, uuid4

from core.clock.clocks import Clock
from core.events.registry import CANONICAL_EVENT_PAYLOAD_SCHEMAS, UnknownEventError
from core.schemas.base import DomainObject
from core.schemas.events import DomainEvent

__all__ = ["EventSink", "InMemoryEventSink", "make_event"]


class EventSink(Protocol):
    """Fan-out target for canonical domain events."""

    def emit(self, event: DomainEvent) -> None: ...


class InMemoryEventSink:
    """Collects emitted events in-process (tests, short-lived tools)."""

    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    def emit(self, event: DomainEvent) -> None:
        self.events.append(event)


def make_event(
    event_name: str,
    payload: DomainObject,
    clock: Clock,
    *,
    producer: str = "execution-engine",
    trace_id: UUID | None = None,
) -> DomainEvent:
    """Build a validated event envelope for a canonical event name."""
    schema = CANONICAL_EVENT_PAYLOAD_SCHEMAS.get(event_name)
    if schema is None:
        raise UnknownEventError(event_name)
    if not isinstance(payload, schema):
        raise TypeError(
            f"payload for {event_name!r} must be {schema.__name__}, got {type(payload).__name__}"
        )
    now = clock.now()
    return DomainEvent(
        event_id=uuid4(),
        trace_id=trace_id,
        event_time=now,
        ingested_at=now,
        producer=producer,
        event_name=event_name,
        payload=payload.canonical_dict(),
        provenance={
            "payload_schema": type(payload).__name__,
            "payload_schema_version": payload.SCHEMA_VERSION,
        },
    )
