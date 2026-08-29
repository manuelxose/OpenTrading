"""Audit tests: immutable entries stamped by the injected clock."""

from __future__ import annotations

from uuid import UUID

from core.audit import AuditLogger, InMemoryAuditSink
from core.clock.clocks import VirtualClock


def test_audit_entry_is_recorded(clock: VirtualClock) -> None:
    sink = InMemoryAuditSink()
    logger = AuditLogger(sink, clock, default_actor="risk-engine")
    entry = logger.record("risk.evaluated", target="proposal-1")

    assert sink.entries == [entry]
    assert entry.actor == "risk-engine"
    assert entry.action == "risk.evaluated"
    assert entry.target == "proposal-1"
    assert entry.outcome == "OK"
    assert entry.timestamp == clock.now()
    assert isinstance(entry.audit_id, UUID)


def test_audit_timestamps_follow_virtual_clock(clock: VirtualClock) -> None:
    from datetime import timedelta

    sink = InMemoryAuditSink()
    logger = AuditLogger(sink, clock)
    first = logger.record("action.one")
    clock.advance(timedelta(minutes=3))
    second = logger.record("action.two")

    assert second.timestamp - first.timestamp == timedelta(minutes=3)
    assert second.timestamp == clock.now()


def test_audit_trace_id_and_metadata(clock: VirtualClock) -> None:
    sink = InMemoryAuditSink()
    logger = AuditLogger(sink, clock)
    trace_id = UUID(int=99)
    entry = logger.record(
        "promotion.approved",
        actor="admin",
        trace_id=trace_id,
        metadata={"strategy": "trend-01"},
    )
    assert entry.trace_id == trace_id
    assert entry.metadata == {"strategy": "trend-01"}
    assert entry.actor == "admin"


def test_audit_entries_are_distinct(clock: VirtualClock) -> None:
    sink = InMemoryAuditSink()
    logger = AuditLogger(sink, clock)
    a = logger.record("action.a")
    b = logger.record("action.a")
    assert a.audit_id != b.audit_id
