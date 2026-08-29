"""Shared fault-injection utilities for the chaos/recovery suite.

Every outage in this package is injected deterministically at a real seam:

- :class:`ScriptedRedis` — a ``RedisConnection`` double whose outage switch
  makes every Redis command raise ``redis.exceptions.ConnectionError``
  ("terminated"); used with the real :class:`apps.worker.bus.RedisStreamBus`
  so its unattended retry/reconnect behavior is exercised, not re-implemented.
- :class:`TransientOutage` — wraps any store and raises a configured error for
  the next N calls of chosen methods ("PostgreSQL restart", "MinIO outage",
  "FalkorDB outage") — the production stores fail the same way.
- :class:`SwitchableTradingAgentsAdapter` — the TradingAgents/LLM boundary
  failing with the same error types the live adapter raises when its timeout
  budget is exhausted or the upstream crashes.
- :class:`GuardedProbeStage` — an idempotent pipeline stage that persists its
  side effect before any post-write work, so crash/outage redelivery can be
  proven exactly-once (mirrors the real stage contract in
  :class:`apps.worker.stages.base.Stage`).
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from datetime import datetime
from typing import Any
from uuid import UUID

import redis.exceptions as redis_exc
from adapters.tradingagents.errors import TradingAgentsError
from apps.worker.stages.base import Stage, StageRuntime
from core.domain.enums import PipelineStageName
from core.schemas.events import DomainEvent
from sqlalchemy.exc import OperationalError

__all__ = [
    "GuardedProbeStage",
    "ScriptedRedis",
    "SwitchableTradingAgentsAdapter",
    "TransientOutage",
    "operational_error",
]


def operational_error() -> OperationalError:
    """A realistic PostgreSQL connectivity failure (server restart window)."""
    return OperationalError(
        "SELECT 1", {}, Exception("connection to server was lost mid-transaction")
    )


class ScriptedRedis:
    """Minimal faithful ``RedisConnection`` double for one RedisStreamBus.

    Streams and consumer groups behave like the real server (XADD / XGROUP /
    XREADGROUP '>' and '0' / XACK / XPENDING / XAUTOCLAIM / XLEN / XDEL).
    ``down`` simulates a terminated Redis: every command raises
    ``redis.exceptions.ConnectionError`` until it is restored.
    """

    def __init__(self) -> None:
        self.down = False
        self._streams: dict[str, list[tuple[str, dict[str, str]]]] = {}
        # (stream, group) -> {"cursor": id, "pel": {id: [consumer, deliveries, mono]}}
        self._groups: dict[tuple[str, str], dict[str, Any]] = {}
        self._counter = 0
        self._mono: dict[float, float] = {}
        self._tick = 0.0

    # ── outage switch ─────────────────────────────────────────────────────

    def terminate(self) -> None:
        self.down = True

    def restore(self) -> None:
        self.down = False

    def _guard(self) -> None:
        if self.down:
            raise redis_exc.ConnectionError("Connection refused: redis is down")

    def _next_id(self) -> str:
        self._counter += 1
        return f"{self._counter}-0"

    def _advance_clock(self) -> float:
        self._tick += 0.001  # deterministic monotonic progression
        return self._tick

    # ── protocol surface (RedisConnection) ────────────────────────────────

    def xadd(self, name: str, fields: dict[str, Any], maxlen: int | None = None) -> str:
        self._guard()
        message_id = self._next_id()
        self._streams.setdefault(name, []).append(
            (message_id, {key: str(value) for key, value in fields.items()})
        )
        if maxlen is not None:
            self._streams[name] = self._streams[name][-maxlen:]
        return message_id

    def xgroup_create(
        self, name: str, groupname: str, id: str = "$", mkstream: bool = False
    ) -> bool:
        self._guard()
        if mkstream:
            self._streams.setdefault(name, [])
        key = (name, groupname)
        if key in self._groups:
            raise redis_exc.ResponseError("BUSYGROUP Consumer Group name already exists")
        self._groups[key] = {"cursor": "0-0", "pel": {}}
        return True

    def xreadgroup(
        self,
        groupname: str,
        consumername: str,
        streams: dict[str, str],
        count: int | None = None,
        block: int | None = None,
        noack: bool = False,
    ) -> Any:
        self._guard()
        output: list[Any] = []
        for name, cursor in streams.items():
            key = (name, groupname)
            if key not in self._groups:
                raise redis_exc.ResponseError(
                    "NOGROUP No such key or consumer group"
                )
            group = self._groups[key]
            stored = self._streams.get(name, [])
            entries: list[tuple[str, dict[str, str]]] = []
            if cursor == ">":
                last_n = int(group["cursor"].split("-")[0])
                for message_id, fields in stored:
                    if int(message_id.split("-")[0]) > last_n:
                        entries.append((message_id, dict(fields)))
            else:  # replay this consumer's own PEL ("0")
                for message_id, pel in group["pel"].items():
                    if pel[0] == consumername:
                        match = next(
                            (fields for mid, fields in stored if mid == message_id), None
                        )
                        if match is not None:
                            entries.append((message_id, dict(match)))
            if count is not None:
                entries = entries[:count]
            if entries:
                for message_id, _fields in entries:
                    pel = group["pel"].get(message_id)
                    if pel is None:
                        group["pel"][message_id] = [
                            consumername,
                            1,
                            self._advance_clock(),
                        ]
                    elif noack is False:
                        pel[1] += 1
                        pel[2] = self._advance_clock()
                    if cursor == ">":
                        group["cursor"] = message_id
                output.append([name, entries])
        return output

    def xack(self, name: str, groupname: str, *ids: str) -> int:
        self._guard()
        key = (name, groupname)
        group = self._groups.get(key)
        if group is None:
            return 0
        removed = 0
        for message_id in ids:
            if group["pel"].pop(message_id, None) is not None:
                removed += 1
        return removed

    def xautoclaim(
        self,
        name: str,
        groupname: str,
        consumername: str,
        min_idle_time: int,
        start_id: str = "0-0",
        count: int | None = None,
    ) -> list[Any]:
        self._guard()
        key = (name, groupname)
        group = self._groups.get(key)
        if group is None:
            return []
        stored = dict(self._streams.get(name, []))
        claimed: list[Any] = []
        for message_id, pel in list(group["pel"].items()):
            idle = (self._tick - pel[2]) * 1000
            if idle < min_idle_time:
                continue
            pel[0] = consumername
            pel[1] += 1
            pel[2] = self._advance_clock()
            fields = dict(stored.get(message_id, {}))
            fields["delivery_count"] = str(pel[1])
            claimed.append([message_id, fields])
            if count is not None and len(claimed) >= count:
                break
        return claimed

    def xpending(
        self, name: str, groupname: str, min: str = "-", max: str = "+", count: int | None = None
    ) -> Any:
        self._guard()
        key = (name, groupname)
        group = self._groups.get(key)
        if group is None:
            return []
        items = [
            {
                "message_id": message_id,
                "consumer": pel[0],
                "time_since_delivered": int((self._tick - pel[2]) * 1000),
                "times_delivered": pel[1],
            }
            for message_id, pel in group["pel"].items()
        ]
        return items[:count] if count is not None else items

    def xlen(self, name: str) -> int:
        self._guard()
        return len(self._streams.get(name, []))

    def xdel(self, name: str, *ids: str) -> int:
        self._guard()
        removed = 0
        keep: list[tuple[str, dict[str, str]]] = []
        for message_id, fields in self._streams.get(name, []):
            if message_id in ids:
                removed += 1
            else:
                keep.append((message_id, fields))
        self._streams[name] = keep
        return removed

    def close(self) -> None:
        return None

    # ── assertions helpers ────────────────────────────────────────────────

    def stream(self, name: str) -> list[tuple[str, dict[str, str]]]:
        return list(self._streams.get(name, []))


class TransientOutage:
    """Wraps any collaborator; the next N calls of ``fail_methods`` raise.

    Models a dependency restart: the underlying object is unharmed (it "comes
    back" — that is what the store/database restart preserves) and
    :meth:`recover` ends the outage window.
    """

    def __init__(
        self,
        wrapped: Any,
        *,
        fail_methods: Collection[str],
        failures: int = 1,
        error_factory: Callable[[], Exception] = operational_error,
    ) -> None:
        self._wrapped = wrapped
        self._fail_methods = frozenset(fail_methods)
        self._remaining = failures
        self._error_factory = error_factory
        self.failures_injected = 0

    def recover(self) -> None:
        self._remaining = 0

    @property
    def remaining(self) -> int:
        return self._remaining

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._wrapped, name)
        if name not in self._fail_methods or not callable(attr):
            return attr

        def guarded(*args: Any, **kwargs: Any) -> Any:
            if self._remaining > 0:
                self._remaining -= 1
                self.failures_injected += 1
                raise self._error_factory()
            return attr(*args, **kwargs)

        return guarded


class SwitchableTradingAgentsAdapter:
    """TradingAgents boundary that can be failed and healed mid-run.

    Raises the same typed errors the live adapter emits: a timeout budget
    exhaustion or an upstream crash. Everything else delegates to the injected
    mock so the full mapper contract is still exercised.
    """

    def __init__(
        self,
        inner: Any,
        *,
        error: type[TradingAgentsError] | None = None,
        clock_now: Callable[[], datetime] | None = None,
    ) -> None:
        self._inner = inner
        self._error = error
        self._clock_now = clock_now
        self.fail = False
        self.runs = 0

    def run(
        self,
        request: Any,
        snapshot: Any = None,
        *,
        trace_id: UUID | None = None,
        now: datetime | None = None,
    ) -> Any:
        self.runs += 1
        if self.fail and self._error is not None:
            raise self._error("injected outage at the TradingAgents boundary")
        return self._inner.run(request, snapshot, trace_id=trace_id, now=now)


class GuardedProbeStage(Stage):
    """Idempotent probe stage: persists its side effect before any crash point.

    - the pipeline-store context fragment is the durable "output" (the guard);
    - ``crash``: when set, the first processing attempt is killed with
      ``SystemExit`` *after* the side effect is persisted — a hard process
      death (not catchable as ``Exception``) exactly like a worker killed
      mid-stage.
    """

    name = PipelineStageName.FUSION
    consumes = ("market.snapshot.created",)
    producer = "chaos.probe"

    def __init__(self) -> None:
        self.calls = 0
        self.crash: bool = False

    def process(self, rt: StageRuntime, event: DomainEvent) -> list[DomainEvent]:
        self.calls += 1
        trace_id = event.trace_id
        assert trace_id is not None
        if rt.store.get_context(trace_id) is not None:
            return []  # already produced — redelivery after crash/restart
        rt.store.save_context_fragment(
            trace_id,
            "probe",
            {"produced": True, "attempt": self.calls},
            instrument_id="EURUSD",
            updated_at=rt.clock.now(),
        )
        if self.crash and self.calls == 1:
            raise SystemExit("worker killed mid-stage (simulated SIGKILL)")
        return []
