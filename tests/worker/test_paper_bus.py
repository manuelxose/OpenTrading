"""Stream bus semantics: delivery, PEL recovery, dead-lettering, reconnect."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from apps.worker.bus import (
    BusUnavailableError,
    InMemoryStreamBus,
    RedisStreamBus,
)
from core.clock.clocks import Clock, SystemClock, VirtualClock
from core.events.envelope import build_domain_event
from core.events.registry import UnknownEventError
from core.schemas.events import DomainEvent

from factories import make_market_snapshot


@pytest.fixture
def vclock() -> VirtualClock:
    return VirtualClock(datetime(2026, 8, 27, tzinfo=UTC))


def snapshot_event(clock: Clock, instrument_id: str = "EURUSD") -> DomainEvent:
    payload = make_market_snapshot(clock.now(), instrument_id=instrument_id, source="bus-tests")
    return build_domain_event(
        event_name="market.snapshot.created",
        payload=payload,
        clock=clock,
        producer="bus-tests",
        trace_id=uuid4(),
    )


class TestInMemoryStreamBus:
    def test_publish_and_read_new(self, vclock: VirtualClock) -> None:
        bus = InMemoryStreamBus(clock=vclock)
        event = snapshot_event(vclock)
        message_id = bus.publish(event)
        bus.ensure_group("g1")
        messages = bus.read_new("g1", "c1", count=10, block_ms=0)
        assert len(messages) == 1
        assert messages[0].message_id == message_id
        assert messages[0].event.event_name == "market.snapshot.created"
        assert messages[0].event.trace_id == event.trace_id

    def test_groups_are_isolated(self, vclock: VirtualClock) -> None:
        bus = InMemoryStreamBus(clock=vclock)
        event = snapshot_event(vclock)
        bus.publish(event)
        bus.ensure_group("g1")
        bus.ensure_group("g2")
        assert len(bus.read_new("g1", "c1", count=10, block_ms=0)) == 1
        assert len(bus.read_new("g2", "c2", count=10, block_ms=0)) == 1

    def test_ack_removes_pending(self, vclock: VirtualClock) -> None:
        bus = InMemoryStreamBus(clock=vclock)
        bus.publish(snapshot_event(vclock))
        bus.ensure_group("g1")
        message = bus.read_new("g1", "c1", count=1, block_ms=0)[0]
        assert len(bus.pending("g1")) == 1
        bus.ack("g1", message.message_id)
        assert bus.pending("g1") == []

    def test_claim_stale_redelivers_pending(self, vclock: VirtualClock) -> None:
        bus = InMemoryStreamBus(clock=vclock)
        bus.publish(snapshot_event(vclock))
        bus.ensure_group("g1")
        first = bus.read_new("g1", "c1", count=1, block_ms=0)[0]
        assert first.delivery_count == 1
        # simulate a crash: the message was never acked; time passes
        vclock.advance(timedelta(seconds=10))
        claimed = bus.claim_stale("g1", "c1-restarted", min_idle_ms=1000, count=10)
        assert len(claimed) == 1
        assert claimed[0].delivery_count == 2
        assert bus.pending("g1")[0].delivery_count == 2

    def test_claim_stale_respects_idle_window(self, vclock: VirtualClock) -> None:
        bus = InMemoryStreamBus(clock=vclock)
        bus.publish(snapshot_event(vclock))
        bus.ensure_group("g1")
        bus.read_new("g1", "c1", count=1, block_ms=0)
        vclock.advance(timedelta(milliseconds=500))
        assert bus.claim_stale("g1", "c2", min_idle_ms=1000, count=10) == []
        vclock.advance(timedelta(seconds=1))
        assert len(bus.claim_stale("g1", "c2", min_idle_ms=1000, count=10)) == 1

    def test_dead_letter_archives_and_acks(self, vclock: VirtualClock) -> None:
        bus = InMemoryStreamBus(clock=vclock)
        bus.publish(snapshot_event(vclock))
        bus.ensure_group("g1")
        message = bus.read_new("g1", "c1", count=1, block_ms=0)[0]
        bus.dead_letter("g1", message, "poisoned")
        assert bus.pending("g1") == []
        assert len(bus.dead["g1"]) == 1
        assert bus.dead["g1"][0][2] == "poisoned"


class _FlakyConnection:
    """Fake redis client: fails N times, then delegates to an in-memory dict."""

    def __init__(self, failures: int) -> None:
        self._failures = failures
        self._calls = 0
        self.streams: dict[str, list[str]] = {}
        self.groups: dict[str, set[str]] = {}

    def _check(self) -> None:
        self._calls += 1
        if self._calls <= self._failures:
            from redis.exceptions import ConnectionError

            raise ConnectionError("redis down (injected)")

    def xadd(self, name: str, fields: dict, maxlen: int | None = None) -> str:
        self._check()
        self.streams.setdefault(name, [])
        message_id = f"{len(self.streams[name]) + 1}-0"
        self.streams[name].append(message_id)
        return message_id

    def xgroup_create(
        self, name: str, groupname: str, id: str = "$", mkstream: bool = False
    ) -> bool:
        self._check()
        if groupname in self.groups.get(name, set()):
            from redis.exceptions import ResponseError

            raise ResponseError("BUSYGROUP Consumer Group name already exists")
        self.groups.setdefault(name, set()).add(groupname)
        return True

    def xreadgroup(self, *args: object, **kwargs: object) -> list:
        self._check()
        return []

    def xack(self, name: str, groupname: str, *ids: str) -> int:
        self._check()
        return len(ids)

    def xautoclaim(self, *args: object, **kwargs: object) -> list:
        self._check()
        return []

    def xpending(self, *args: object, **kwargs: object) -> list:
        self._check()
        return []

    def xlen(self, name: str) -> int:
        self._check()
        return len(self.streams.get(name, []))

    def xdel(self, name: str, *ids: str) -> int:
        self._check()
        return 0

    def close(self) -> None:
        pass


class TestRedisStreamBusReconnect:
    def test_publish_succeeds_after_reconnect(self) -> None:
        connection = _FlakyConnection(failures=2)
        bus = RedisStreamBus(
            "redis://fake/0",
            stream_key="ot:events",
            connection_factory=lambda url: connection,
            retry_base_seconds=0.01,
            retry_max_seconds=0.05,
            max_attempts=10,
            clock=SystemClock(),
        )
        event = snapshot_event(SystemClock())
        message_id = bus.publish(event)
        assert message_id == "1-0"
        assert connection._calls >= 3  # two failures + one success

    def test_raises_after_max_attempts(self) -> None:
        connection = _FlakyConnection(failures=10_000)
        bus = RedisStreamBus(
            "redis://fake/0",
            stream_key="ot:events",
            connection_factory=lambda url: connection,
            retry_base_seconds=0.001,
            retry_max_seconds=0.01,
            max_attempts=3,
            clock=SystemClock(),
        )
        with pytest.raises(BusUnavailableError):
            bus.publish(snapshot_event(SystemClock()))

    def test_ensure_group_tolerates_existing_group(self) -> None:
        connection = _FlakyConnection(failures=0)
        bus = RedisStreamBus(
            "redis://fake/0",
            stream_key="ot:events",
            connection_factory=lambda url: connection,
            retry_base_seconds=0.01,
            retry_max_seconds=0.05,
            max_attempts=5,
            clock=SystemClock(),
        )
        bus.ensure_group("g1")
        bus.ensure_group("g1")  # BUSYGROUP handled inside


def test_unknown_event_name_rejected(vclock: VirtualClock) -> None:
    payload = make_market_snapshot(vclock.now())
    with pytest.raises(UnknownEventError):
        build_domain_event(
            event_name="not.a.canonical.event",
            payload=payload,
            clock=vclock,
            producer="t",
        )
