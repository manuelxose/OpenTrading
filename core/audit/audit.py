"""Structured audit trail (architecture §13: system_events, audit_events).

Every security- or governance-relevant action is recorded as an immutable
:class:`AuditEntry` through an :class:`AuditLogger` into one or more
:class:`AuditSink` implementations. PostgreSQL persistence lands with Phase 1;
:class:`InMemoryAuditSink` exists now and in tests.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID, uuid4

from pydantic import Field

from core.clock.clocks import Clock
from core.schemas.base import BaseContractModel, UtcDateTime

__all__ = ["AuditEntry", "AuditLogger", "AuditSink", "InMemoryAuditSink"]

AUDIT_SCHEMA_VERSION = "1.0.0"


class AuditEntry(BaseContractModel):
    """One immutable audit record."""

    schema_version: str = Field(default=AUDIT_SCHEMA_VERSION)
    audit_id: UUID
    trace_id: UUID | None = None
    actor: str = Field(min_length=1)
    action: str = Field(min_length=1)
    target: str | None = None
    outcome: str = "OK"
    timestamp: UtcDateTime
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditSink(Protocol):
    def record(self, entry: AuditEntry) -> None: ...


class InMemoryAuditSink:
    """Append-only in-memory sink (tests, short-lived processes)."""

    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    def record(self, entry: AuditEntry) -> None:
        self.entries.append(entry)


class AuditLogger:
    """Creates entries stamped by an injected :class:`Clock` and fans them out to sinks."""

    def __init__(self, sink: AuditSink, clock: Clock, default_actor: str = "system") -> None:
        self._sink = sink
        self._clock = clock
        self._default_actor = default_actor

    def record(
        self,
        action: str,
        *,
        actor: str | None = None,
        target: str | None = None,
        trace_id: UUID | None = None,
        outcome: str = "OK",
        metadata: dict[str, Any] | None = None,
    ) -> AuditEntry:
        entry = AuditEntry(
            audit_id=uuid4(),
            trace_id=trace_id,
            actor=actor or self._default_actor,
            action=action,
            target=target,
            outcome=outcome,
            timestamp=self._clock.now(),
            metadata=metadata or {},
        )
        self._sink.record(entry)
        return entry
