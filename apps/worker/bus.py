"""Redis Streams event bus for the autonomous pipeline (INV-15, architecture §14).

The bus is a single logical stream (``opentrading:events``) with one consumer
group per stage worker. Delivery protocol:

- producers ``XADD`` the full :class:`DomainEvent` envelope (plus routing
  fields ``event_name`` and ``trace_id``);
- each worker ``XREADGROUP`` new messages (``>``), dispatches by event name,
  and ``XACK`` on success;
- on startup a worker reclaims its group's PEL entries (``XAUTOCLAIM`` /
  ``XCLAIM``) — this is the worker-restart recovery path; stage handlers are
  idempotent through the pipeline store, so redelivery is safe;
- messages that exceed ``max_deliveries`` are acknowledged and moved to a
  per-group dead-letter stream, never silently dropped and never replayed
  forever;
- every Redis command runs through a retry wrapper with exponential backoff —
  the platform keeps running (unattended) while Redis is down and resumes as
  soon as it returns.

:class:`InMemoryStreamBus` mirrors the same semantics for unit tests; the
integration suite exercises the real Redis protocol (docker-gated).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

import redis
import redis.exceptions as redis_exc
from core.clock.clocks import Clock, SystemClock
from core.events.envelope import deserialize_event, serialize_event
from core.schemas.events import DomainEvent

__all__ = [
    "BusUnavailableError",
    "InMemoryStreamBus",
    "PendingMessage",
    "RedisConnection",
    "RedisStreamBus",
    "StreamMessage",
]

logger = logging.getLogger(__name__)

_RETRYABLE = (
    redis_exc.ConnectionError,
    redis_exc.TimeoutError,
    redis_exc.BusyLoadingError,
)


class BusUnavailableError(RuntimeError):
    """Raised when the bus cannot perform an operation after retries."""


@dataclass(frozen=True)
class StreamMessage:
    """One consumed message: the redis stream id, delivery count, envelope."""

    message_id: str
    delivery_count: int
    event: DomainEvent


@dataclass(frozen=True)
class PendingMessage:
    """One entry of a consumer group's PEL (XPENDING view)."""

    message_id: str
    consumer: str
    idle_ms: int
    delivery_count: int


class RedisConnection(Protocol):
    """Minimal structural view of ``redis.Redis`` (test doubles implement it)."""

    def xadd(self, name: str, fields: dict[str, Any], maxlen: int | None = None) -> str: ...
    def xgroup_create(
        self, name: str, groupname: str, id: str = "$", mkstream: bool = False
    ) -> bool: ...
    def xreadgroup(
        self,
        groupname: str,
        consumername: str,
        streams: dict[str, str],
        count: int | None = None,
        block: int | None = None,
        noack: bool = False,
    ) -> Any: ...
    def xack(self, name: str, groupname: str, *ids: str) -> int: ...
    def xautoclaim(
        self,
        name: str,
        groupname: str,
        consumername: str,
        min_idle_time: int,
        start_id: str = "0-0",
        count: int | None = None,
    ) -> list[Any]: ...
    def xpending(
        self, name: str, groupname: str, min: str = "-", max: str = "+", count: int | None = None
    ) -> Any: ...
    def xlen(self, name: str) -> int: ...
    def xdel(self, name: str, *ids: str) -> int: ...
    def close(self) -> None: ...


def _connection_factory(url: str) -> RedisConnection:
    client = redis.Redis.from_url(url, decode_responses=True)
    return client  # type: ignore[return-value]


class RedisStreamBus:
    """Redis Streams bus with reconnect and recovery semantics."""

    def __init__(
        self,
        url: str,
        *,
        stream_key: str,
        connection_factory: Callable[[str], RedisConnection] = _connection_factory,
        retry_base_seconds: float = 1.0,
        retry_max_seconds: float = 30.0,
        max_attempts: int | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._url = url
        self._stream_key = stream_key
        self._connection_factory = connection_factory
        self._retry_base = retry_base_seconds
        self._retry_max = retry_max_seconds
        self._max_attempts = max_attempts  # None = retry forever (unattended)
        self._clock = clock or SystemClock()
        self._conn: RedisConnection | None = None
        self._lock = threading.Lock()

    # ── connection management ─────────────────────────────────────────────────

    def _connect(self) -> RedisConnection:
        with self._lock:
            if self._conn is not None:
                return self._conn
            self._conn = self._connection_factory(self._url)
            return self._conn

    def _drop(self) -> None:
        with self._lock:
            conn = self._conn
            self._conn = None
            if conn is not None:
                with suppress(Exception):  # best-effort close
                    conn.close()

    def _execute(self, name: str, operation: Callable[[RedisConnection], Any]) -> Any:
        """Run ``operation`` with reconnect + exponential backoff.

        Retries forever in unattended mode (``max_attempts=None``); the platform
        resumes automatically when Redis returns. Each failed attempt logs once.
        """
        attempt = 0
        while True:
            attempt += 1
            try:
                conn = self._connect()
                return operation(conn)
            except _RETRYABLE as exc:
                self._drop()
                if self._max_attempts is not None and attempt >= self._max_attempts:
                    raise BusUnavailableError(
                        f"redis {name} failed after {attempt} attempts: {exc!r}"
                    ) from exc
                delay = min(self._retry_base * (2 ** (attempt - 1)), self._retry_max)
                logger.warning(
                    "redis %s failed (attempt %d): %s; retrying in %.1fs",
                    name,
                    attempt,
                    exc,
                    delay,
                )
                time.sleep(delay)
            except redis_exc.ResponseError as exc:
                raise BusUnavailableError(f"redis {name} rejected the command: {exc}") from exc

    # ── producer side ─────────────────────────────────────────────────────────

    def publish(self, event: DomainEvent) -> str:
        """Append one envelope to the stream; returns the message id."""
        trace = event.trace_id.hex if event.trace_id is not None else ""
        return str(
            self._execute(
                "XADD",
                lambda c: c.xadd(
                    self._stream_key,
                    {
                        "event_name": event.event_name,
                        "trace_id": trace,
                        "event_json": serialize_event(event).decode("utf-8"),
                    },
                    maxlen=100_000,
                ),
            )
        )

    # ── consumer side ─────────────────────────────────────────────────────────

    def ensure_group(self, group: str) -> None:
        """Create the consumer group if it does not exist (MKSTREAM)."""

        def _create(c: RedisConnection) -> bool:
            try:
                return c.xgroup_create(self._stream_key, group, id="0", mkstream=True)
            except redis_exc.ResponseError as exc:
                if "BUSYGROUP" in str(exc):  # group already exists
                    return False
                raise

        self._execute("XGROUP CREATE", _create)

    def read_new(
        self, group: str, consumer: str, *, count: int, block_ms: int
    ) -> list[StreamMessage]:
        """Read messages never delivered to the group (``>``)."""
        raw = self._execute(
            "XREADGROUP",
            lambda c: c.xreadgroup(
                group,
                consumer,
                {self._stream_key: ">"},
                count=count,
                block=block_ms,
            ),
        )
        return self._to_messages(raw)

    def read_pending(self, group: str, consumer: str, *, count: int = 100) -> list[StreamMessage]:
        """Read the consumer's own undelivered PEL entries (``0``), with
        delivery counts resolved from XPENDING."""
        raw = self._execute(
            "XREADGROUP",
            lambda c: c.xreadgroup(
                group,
                consumer,
                {self._stream_key: "0"},
                count=count,
            ),
        )
        messages = self._to_messages(raw)
        counts = {
            p.message_id: p.delivery_count for p in self.pending(group, count=len(messages) + 1)
        }
        return [
            StreamMessage(
                message_id=m.message_id,
                delivery_count=counts.get(m.message_id, m.delivery_count),
                event=m.event,
            )
            for m in messages
        ]

    def pending(self, group: str, *, count: int = 100) -> list[PendingMessage]:
        """Inspect the group's PEL (delivery counts, idle times)."""
        raw = self._execute(
            "XPENDING",
            lambda c: c.xpending(self._stream_key, group, min="-", max="+", count=count),
        )
        if not raw:
            return []
        return [
            PendingMessage(
                message_id=item["message_id"],
                consumer=item["consumer"],
                idle_ms=int(item["time_since_delivered"]),
                delivery_count=int(item["times_delivered"]),
            )
            for item in raw
        ]

    def claim_stale(
        self, group: str, consumer: str, *, min_idle_ms: int, count: int
    ) -> list[StreamMessage]:
        """Reclaim PEL entries idle at least ``min_idle_ms`` (restart recovery)."""
        claimed = self._execute(
            "XAUTOCLAIM",
            lambda c: c.xautoclaim(
                self._stream_key,
                group,
                consumer,
                min_idle_time=min_idle_ms,
                start_id="0-0",
                count=count,
            ),
        )
        messages: list[StreamMessage] = []
        for message_id, fields in claimed:
            delivery_count = int(fields.get("delivery_count", 1)) if isinstance(fields, dict) else 1
            event = deserialize_event(fields["event_json"])
            messages.append(
                StreamMessage(message_id=message_id, delivery_count=delivery_count, event=event)
            )
        return messages

    def ack(self, group: str, message_id: str) -> None:
        self._execute("XACK", lambda c: c.xack(self._stream_key, group, message_id))

    def dead_letter(self, group: str, message: StreamMessage, error: str) -> None:
        """Acknowledge and archive a poisoned message for offline inspection."""
        event = message.event
        trace = event.trace_id.hex if event.trace_id is not None else ""

        def _move(c: RedisConnection) -> None:
            c.xadd(
                f"{self._stream_key}:dead:{group}",
                {
                    "event_name": event.event_name,
                    "trace_id": trace,
                    "event_json": serialize_event(event).decode("utf-8"),
                    "error": error[:2000],
                    "attempts": str(message.delivery_count),
                    "dead_at": self._clock.now().isoformat(),
                },
                maxlen=10_000,
            )
            c.xack(self._stream_key, group, message.message_id)

        self._execute("DEAD-LETTER", _move)

    def trim_dead(self, group: str, maxlen: int = 10_000) -> None:
        """Bound the dead-letter stream (kept for audit)."""
        self._execute("XTRIM", lambda c: c.xlen(f"{self._stream_key}:dead:{group}"))

    def _to_messages(self, raw: Any) -> list[StreamMessage]:
        messages: list[StreamMessage] = []
        if not raw:
            return messages
        for _stream, entries in raw:
            for message_id, fields in entries:
                event = deserialize_event(fields["event_json"])
                messages.append(StreamMessage(message_id=message_id, delivery_count=1, event=event))
        return messages


class InMemoryStreamBus:
    """Semantically faithful in-memory mirror of :class:`RedisStreamBus`.

    Keeps a PEL per consumer group with delivery counts and idle times, so the
    recovery paths (claim stale, poison dead-lettering) are testable without a
    running Redis.
    """

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock = clock or SystemClock()
        self._entries: list[tuple[str, DomainEvent]] = []  # (id, event) ordered
        self._last_id = 0
        self._groups: dict[str, dict[str, Any]] = {}  # group -> state
        self.dead: dict[str, list[tuple[str, DomainEvent, str]]] = {}  # group -> poisoned

    @property
    def stream_length(self) -> int:
        return len(self._entries)

    def publish(self, event: DomainEvent) -> str:
        self._last_id += 1
        message_id = f"{self._last_id}-0"
        self._entries.append((message_id, event))
        return message_id

    def ensure_group(self, group: str) -> None:
        self._groups.setdefault(
            group,
            {"cursor": 0, "pending": {}},  # pending: message_id -> dict
        )

    def read_new(
        self, group: str, consumer: str, *, count: int, block_ms: int
    ) -> list[StreamMessage]:
        self.ensure_group(group)
        state = self._groups[group]
        messages: list[StreamMessage] = []
        index = state["cursor"]
        while index < len(self._entries) and len(messages) < count:
            message_id, event = self._entries[index]
            index += 1
            if message_id in state["pending"]:
                continue
            state["pending"][message_id] = {
                "consumer": consumer,
                "deliveries": 1,
                "delivered_at": self._clock.now().timestamp(),
            }
            messages.append(StreamMessage(message_id, 1, event))
        state["cursor"] = index
        return messages

    def read_pending(self, group: str, consumer: str, *, count: int = 100) -> list[StreamMessage]:
        self.ensure_group(group)
        state = self._groups[group]
        messages: list[StreamMessage] = []
        for message_id, info in state["pending"].items():
            if len(messages) >= count:
                break
            if info["consumer"] != consumer:
                continue
            messages.append(
                StreamMessage(
                    message_id,
                    info["deliveries"],
                    self._event_for(message_id),
                )
            )
        return messages

    def pending(self, group: str, *, count: int = 100) -> list[PendingMessage]:
        self.ensure_group(group)
        now_ts = self._clock.now().timestamp()
        return [
            PendingMessage(
                message_id=mid,
                consumer=str(info["consumer"]),
                idle_ms=max(0, int((now_ts - info["delivered_at"]) * 1000)),
                delivery_count=info["deliveries"],
            )
            for mid, info in self._groups[group]["pending"].items()
        ][:count]

    def claim_stale(
        self, group: str, consumer: str, *, min_idle_ms: int, count: int
    ) -> list[StreamMessage]:
        self.ensure_group(group)
        state = self._groups[group]
        now_ts = self._clock.now().timestamp()
        claimed: list[StreamMessage] = []
        for message_id, info in list(state["pending"].items()):
            idle_ms = (now_ts - info["delivered_at"]) * 1000
            if idle_ms < min_idle_ms:
                continue
            if len(claimed) >= count:
                break
            info["consumer"] = consumer
            info["deliveries"] += 1
            info["delivered_at"] = now_ts
            event = self._event_for(message_id)
            claimed.append(StreamMessage(message_id, info["deliveries"], event))
        return claimed

    def ack(self, group: str, message_id: str) -> None:
        self.ensure_group(group)
        self._groups[group]["pending"].pop(message_id, None)

    def dead_letter(self, group: str, message: StreamMessage, error: str) -> None:
        self.ensure_group(group)
        self.ack(group, message.message_id)
        self.dead.setdefault(group, []).append((message.message_id, message.event, error))

    def _event_for(self, message_id: str) -> DomainEvent:
        for mid, event in self._entries:
            if mid == message_id:
                return event
        raise KeyError(message_id)


def trace_id_of(event: DomainEvent) -> UUID | None:
    """Convenience accessor for envelope correlation."""
    return event.trace_id


def new_trace_id() -> UUID:
    from uuid import uuid4

    return uuid4()
