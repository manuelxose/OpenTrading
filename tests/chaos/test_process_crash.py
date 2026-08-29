"""Process crash scenarios: worker, API, and the Core ↔ MT4 heartbeat.

- **Worker crash** — killed between stage success and ACK (hard ``SystemExit``,
  not catchable by the loop): the restart reclaims the PEL entry and stage
  idempotency makes redelivery a no-op (no duplicate work). Killed *mid-stage*
  after persisting its side effect: the idempotent guard prevents a second
  side effect on redelivery.
- **API crash** — the API is stateless: a fresh instance serves identically,
  ``/readyz`` degrades to 503 while a dependency is down and recovers, and
  ``/healthz`` stays alive throughout.
- **MT4 disconnect** — heartbeat loss engages the dead-man switch: the
  persisted safe execution state blocks new entries without touching broker
  positions, and a returning heartbeat clears it.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from adapters.mt4.broker import BrokerConfig, SymbolSpec
from adapters.mt4.client import Mt4ExecutionClient
from adapters.mt4.emulator import Mt4Emulator
from adapters.mt4.protocol import HeartbeatEvent, Mt4MessageType, WireMessage
from adapters.mt4.transport import ConnectionHealth, Mt4Endpoints
from apps.api.main import create_app
from apps.worker.pipeline import StageWorker
from core.clock.clocks import SystemClock, VirtualClock
from core.config.settings import get_settings
from core.domain.enums import OrderState
from core.events.envelope import build_domain_event
from core.schemas.events import DomainEvent
from engines.execution.emergency import (
    DeadManSwitchReason,
    EmergencyControlViolation,
    EmergencyPolicy,
)
from engines.execution.persistence import InMemoryExecutionStateStore
from engines.execution.service import ExecutionService
from fastapi.testclient import TestClient

from chaos_faults import GuardedProbeStage
from execution_helpers import Stack, make_intent
from factories import make_market_snapshot
from worker_helpers import build_paper_stack, scripted_snapshots

NOW = datetime(2026, 8, 27, tzinfo=UTC)

EURUSD = SymbolSpec(
    initial_mid=Decimal("1.08000"),
    spread=Decimal("0.00012"),
    max_spread=Decimal("0.0003"),
)


def _snapshot_event(clock: VirtualClock) -> DomainEvent:
    payload = make_market_snapshot(clock.now(), source="chaos-process")
    return build_domain_event(
        event_name="market.snapshot.created",
        payload=payload,
        clock=clock,
        producer="chaos-tests",
        trace_id=uuid4(),
    )


def _make_runtime(clock: VirtualClock):
    stack = build_paper_stack(
        clock=clock, settings=get_settings(), source=scripted_snapshots()
    )
    return stack


class _CrashOnAckBus:
    """Simulates a worker killed after processing but before the ACK landed."""

    def __init__(self, inner: object) -> None:
        self._inner = inner
        self.crashed = False

    def __getattr__(self, name: str):
        attr = getattr(self._inner, name)
        if name != "ack":
            return attr

        def ack(*args: object, **kwargs: object) -> object:
            if not self.crashed:
                self.crashed = True
                raise SystemExit("worker killed between publish and ACK")
            return attr(*args, **kwargs)

        return ack


class TestWorkerCrash:
    def test_crash_after_process_restart_never_duplicates_work(self) -> None:
        clock = VirtualClock(NOW)
        stack = _make_runtime(clock)
        probe = GuardedProbeStage()
        crash_bus = _CrashOnAckBus(stack.bus)
        worker = StageWorker(
            group="ot:fusion",
            consumer="worker-1",
            stages=[probe],
            rt=stack.rt,
            bus=crash_bus,  # type: ignore[arg-type]
            clock=clock,
        )
        worker.start()
        event = _snapshot_event(clock)
        stack.bus.publish(event)

        # The stage succeeded (run record SUCCEEDED, side effect persisted)
        # and the process died before the ACK.
        with pytest.raises(SystemExit):
            worker.run_iteration()
        length_after_crash = stack.bus.stream_length
        assert probe.calls == 1
        assert len(stack.bus.pending("ot:fusion")) == 1
        context = stack.store.get_context(event.trace_id)
        assert context is not None and context.fragments["probe"]["produced"] is True

        # Restart: a fresh worker reclaims the stale entry; stage idempotency
        # makes the redelivery a no-op — nothing is reprocessed or re-published.
        clock.advance(timedelta(milliseconds=stack.config.bus.claim_idle_ms + 100))
        restarted = StageWorker(
            group="ot:fusion",
            consumer="worker-2",
            stages=[probe],
            rt=stack.rt,
            bus=stack.bus,
            clock=clock,
        )
        restarted.start()
        restarted.run_iteration()
        assert probe.calls == 1  # never reprocessed
        assert stack.bus.pending("ot:fusion") == []
        assert stack.bus.stream_length == length_after_crash  # nothing re-published

    def test_crash_mid_stage_guard_prevents_duplicate_side_effects(self) -> None:
        clock = VirtualClock(NOW)
        stack = _make_runtime(clock)
        probe = GuardedProbeStage()
        probe.crash = True
        worker = StageWorker(
            group="ot:fusion",
            consumer="worker-1",
            stages=[probe],
            rt=stack.rt,
            bus=stack.bus,
            clock=clock,
        )
        worker.start()
        event = _snapshot_event(clock)
        stack.bus.publish(event)

        # Killed after the side effect was persisted (hard crash: SystemExit).
        with pytest.raises(SystemExit):
            worker.run_iteration()
        assert probe.calls == 1
        assert len(stack.bus.pending("ot:fusion")) == 1
        context = stack.store.get_context(event.trace_id)
        assert context is not None
        assert context.fragments["probe"]["attempt"] == 1  # persisted before the kill

        # Redelivery reprocesses, but the guard makes the write exactly-once.
        clock.advance(timedelta(milliseconds=stack.config.bus.claim_idle_ms + 100))
        restarted = StageWorker(
            group="ot:fusion",
            consumer="worker-2",
            stages=[probe],
            rt=stack.rt,
            bus=stack.bus,
            clock=clock,
        )
        restarted.start()
        restarted.run_iteration()
        assert probe.calls == 2
        assert stack.bus.pending("ot:fusion") == []
        context = stack.store.get_context(event.trace_id)
        assert context is not None
        assert context.fragments["probe"]["attempt"] == 1  # the side effect was NOT repeated
        run = stack.store.get_run(event.trace_id, probe.name)
        assert run is not None and run.status.value == "SUCCEEDED"


# ── API crash ────────────────────────────────────────────────────────────────


async def _check_ok(settings: object) -> None:
    return None


async def _check_down(settings: object) -> None:
    raise RuntimeError("connection refused")


def _readiness_checks(redis_state: str) -> list[tuple[str, object]]:
    redis_check = _check_ok if redis_state == "ok" else _check_down
    return [
        ("postgres", _check_ok),
        ("redis", redis_check),
        ("minio", _check_ok),
        ("falkordb", _check_ok),
    ]


class TestApiCrash:
    def test_crash_restart_degrades_and_recovers_readiness(self) -> None:
        settings = get_settings()

        # Instance 1 (healthy).
        client = TestClient(
            create_app(settings=settings, readiness_checks=_readiness_checks("ok"))
        )
        response = client.get("/readyz")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"
        contracts_before = client.get("/api/v1/contracts").json()

        # "Crash": the process dies with it — the next instance starts from
        # scratch while a dependency (redis) is down.
        del client
        degraded = TestClient(
            create_app(settings=settings, readiness_checks=_readiness_checks("down"))
        )
        response = degraded.get("/readyz")
        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "degraded"
        checks = {check["name"]: check for check in body["checks"]}
        assert checks["redis"]["status"] == "unavailable"
        # Liveness is independent of dependencies.
        assert degraded.get("/healthz").status_code == 200
        # No state is carried between process incarnations.
        assert degraded.get("/api/v1/contracts").json() == contracts_before

        # The dependency returns: a fresh instance reports ready again.
        recovered = TestClient(
            create_app(settings=settings, readiness_checks=_readiness_checks("ok"))
        )
        assert recovered.get("/readyz").status_code == 200


# ── MT4 disconnect → dead-man switch ─────────────────────────────────────────


def _collect(
    client: Mt4ExecutionClient,
    predicate: Callable[[WireMessage], bool],
    *,
    deadline_seconds: float = 5.0,
    poll_ms: int = 50,
) -> list[WireMessage]:
    found: list[WireMessage] = []
    start = time.monotonic()
    while time.monotonic() - start < deadline_seconds:
        found.extend(client.drain_events(timeout_ms=poll_ms))
        if any(predicate(event) for event in found):
            break
    return found


@pytest.fixture()
def emulator() -> Iterator[Mt4Emulator]:
    emu = Mt4Emulator(
        SystemClock(),
        endpoints=Mt4Endpoints(
            command_addr="tcp://127.0.0.1:*",
            events_addr="tcp://127.0.0.1:*",
            quotes_addr="tcp://127.0.0.1:*",
        ),
        broker_config=BrokerConfig(symbols={"EURUSD": EURUSD}),
        seed=23,
        heartbeat_interval_seconds=0.1,
        quote_interval_seconds=0.05,
    )
    emu.start()
    yield emu
    emu.stop()


def _connect(emulator: Mt4Emulator, *, timeout: float = 1.0) -> Mt4ExecutionClient:
    client = Mt4ExecutionClient(
        SystemClock(),
        endpoints=emulator.endpoints,
        request_timeout_seconds=timeout,
        degraded_after_seconds=0.6,
        down_after_seconds=1.2,
    )
    client.connect()
    _collect(client, lambda e: e.message_type is Mt4MessageType.HEARTBEAT)
    assert client.connection_health() is ConnectionHealth.CONNECTED
    return client


def _service(
    store: InMemoryExecutionStateStore, stack: Stack, client: Mt4ExecutionClient
) -> ExecutionService:
    return ExecutionService(
        store=store,
        applier=stack.applier,
        reconciler=stack.reconciler,
        controller=stack.controller,
        client=client,
        clock=stack.clock,
        audit=stack.audit,
        events=stack.events,
        emergency=stack.emergency,
    )


def _feed_heartbeats(service: ExecutionService, deadline_seconds: float = 3.0) -> bool:
    start = time.monotonic()
    while time.monotonic() - start < deadline_seconds:
        drained = service.drain_events(timeout_ms=100)
        if any(isinstance(event, HeartbeatEvent) for event in drained):
            return True
    return False


class TestMt4Disconnect:
    def test_heartbeat_loss_engages_safe_state_blocks_entries_and_recovers(
        self, emulator: Mt4Emulator
    ) -> None:
        store = InMemoryExecutionStateStore()
        stack = Stack(
            store=store,
            clock=SystemClock(),
            policy=EmergencyPolicy(heartbeat_timeout=timedelta(seconds=1)),
        )
        client = _connect(emulator)
        service = _service(store, stack, client)

        # Healthy: heartbeats flow through the service into the dead-man switch.
        assert _feed_heartbeats(service)
        service.check_emergency()
        assert stack.emergency.safe_execution_state_active() is False

        # The MT4 bridge disconnects: heartbeats stop.
        emulator.stop()
        client.close()
        time.sleep(1.6)  # past the 1s heartbeat timeout

        # Dead-man switch engages: persisted safe execution state, CRITICAL
        # alert, new entries blocked — broker positions untouched.
        service.check_emergency()
        assert stack.emergency.safe_execution_state_active() is True
        state = stack.emergency.dead_man_state()
        assert DeadManSwitchReason.HEARTBEAT_LOST.value in state.reason_codes
        assert len(stack.alerts.alerts) == 1
        assert stack.alerts.alerts[0].severity == "CRITICAL"
        with pytest.raises(EmergencyControlViolation):
            service.submit(make_intent())
        assert emulator.broker.positions() == ()  # no broker-side action taken

        # The bridge returns: a heartbeat clears the safe state and trading
        # resumes with a clean entry.
        emulator.start()
        recovered_client = _connect(emulator)
        recovered_service = _service(store, stack, recovered_client)
        assert _feed_heartbeats(recovered_service)
        recovered_service.check_emergency()
        assert stack.emergency.safe_execution_state_active() is False

        intent = make_intent()
        record = recovered_service.submit(intent)
        assert record.state is OrderState.FILLED
        assert len(store.list_positions(open_only=True)) == 1
        recovered_client.close()
