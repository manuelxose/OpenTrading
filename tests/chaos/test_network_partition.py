"""Chaos DoD: network partition and unexpected manual broker positions.

- Partition → SAFE_MODE (broker unreachable): new positions blocked, monitoring
  and reconciliation still allowed; recovery after the partition exits cleanly.
- A human places a trade directly at MT4 → reconciliation flags the unknown
  position as MATERIAL → SAFE_MODE + alert.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from decimal import Decimal

import pytest
from adapters.mt4.broker import BrokerConfig, SymbolSpec
from adapters.mt4.client import Mt4ExecutionClient
from adapters.mt4.emulator import Mt4Emulator
from adapters.mt4.protocol import Mt4MessageType, WireMessage
from adapters.mt4.transport import ConnectionHealth, Mt4Endpoints
from core.clock.clocks import SystemClock
from core.domain.enums import OrderState, PositionSide
from engines.execution.persistence import InMemoryExecutionStateStore
from engines.execution.safe_mode import SafeModeViolation
from engines.execution.service import ExecutionService

from execution_helpers import Stack, get_order, make_intent, make_position_snapshot

EURUSD = SymbolSpec(
    initial_mid=Decimal("1.08000"),
    spread=Decimal("0.00012"),
    max_spread=Decimal("0.0003"),
)


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


def _wait_heartbeat(client: Mt4ExecutionClient) -> None:
    _collect(client, lambda e: e.message_type is Mt4MessageType.HEARTBEAT)


def _connect(emulator: Mt4Emulator, *, timeout: float = 1.0) -> Mt4ExecutionClient:
    client = Mt4ExecutionClient(
        SystemClock(),
        endpoints=emulator.endpoints,
        request_timeout_seconds=timeout,
        degraded_after_seconds=0.6,
        down_after_seconds=1.2,
    )
    client.connect()
    _wait_heartbeat(client)
    assert client.connection_health() is ConnectionHealth.CONNECTED
    return client


def _service(store: InMemoryExecutionStateStore, client: Mt4ExecutionClient) -> ExecutionService:
    stack = Stack(store=store, clock=SystemClock())
    return ExecutionService(
        store=stack.store,
        applier=stack.applier,
        reconciler=stack.reconciler,
        controller=stack.controller,
        client=client,
        clock=stack.clock,
        audit=stack.audit,
        events=stack.events,
    )


@pytest.fixture()
def emulator() -> Iterator[Mt4Emulator]:
    clock = SystemClock()
    emu = Mt4Emulator(
        clock,
        endpoints=Mt4Endpoints(
            command_addr="tcp://127.0.0.1:*",
            events_addr="tcp://127.0.0.1:*",
            quotes_addr="tcp://127.0.0.1:*",
        ),
        broker_config=BrokerConfig(symbols={"EURUSD": EURUSD}),
        seed=13,
        heartbeat_interval_seconds=0.1,
        quote_interval_seconds=0.05,
    )
    emu.start()
    yield emu
    emu.stop()


def test_partition_enters_safe_mode_and_recovers(emulator: Mt4Emulator) -> None:
    store = InMemoryExecutionStateStore()
    client = _connect(emulator)
    service = _service(store, client)

    intent = make_intent()
    assert service.submit(intent).state is OrderState.FILLED
    client.close()

    # Partition: the bridge disappears.
    emulator.stop()
    partitioned_client = _connect_client_unsafe(emulator, timeout=0.5)
    partitioned_service = _service(store, partitioned_client)
    outcome = partitioned_service.startup_reconciliation()
    assert outcome.broker_reachable is False
    assert outcome.safe_mode_active is True
    assert store.get_safe_mode().active is True
    assert "BROKER_UNREACHABLE" in store.get_safe_mode().reason_codes

    # SAFE_MODE: monitoring + reconciliation allowed, new positions blocked.
    with pytest.raises(SafeModeViolation):
        partitioned_service.submit(make_intent())
    partitioned_client.close()

    # Recovery: the bridge returns; a clean reconciliation exits SAFE_MODE.
    emulator.start()
    recovered_client = _connect(emulator)
    recovered_service = _service(store, recovered_client)
    recovered = recovered_service.startup_reconciliation()
    assert recovered.broker_reachable is True
    assert recovered.safe_mode_active is False
    assert store.get_safe_mode().active is False

    second = make_intent()
    assert recovered_service.submit(second).state is OrderState.FILLED
    assert get_order(store, second.order_intent_id).state is OrderState.FILLED
    recovered_client.close()


def _connect_client_unsafe(emulator: Mt4Emulator, *, timeout: float) -> Mt4ExecutionClient:
    client = Mt4ExecutionClient(
        SystemClock(),
        endpoints=emulator.endpoints,
        request_timeout_seconds=timeout,
        degraded_after_seconds=0.6,
        down_after_seconds=1.2,
    )
    client.connect()
    return client


def test_unexpected_manual_broker_position_enters_safe_mode(emulator: Mt4Emulator) -> None:
    """A human trades directly at MT4: the position is material and must flip
    the platform into SAFE_MODE with an alert."""
    store = InMemoryExecutionStateStore()
    stack = Stack(store=store, clock=SystemClock())

    now = SystemClock().now()
    emulator.broker.open_manual_position(
        make_position_snapshot(
            now,
            position_id="manual-1",
            strategy_id=None,
            instrument_id="EURUSD",
            side=PositionSide.LONG,
            quantity=Decimal("1.00"),
            average_entry_price=Decimal("1.08000"),
            order_intent_id=None,  # the platform never sent this
        )
    )

    client = _connect(emulator)
    service = ExecutionService(
        store=stack.store,
        applier=stack.applier,
        reconciler=stack.reconciler,
        controller=stack.controller,
        client=client,
        clock=stack.clock,
        audit=stack.audit,
        events=stack.events,
    )
    outcome = service.startup_reconciliation()
    assert outcome.safe_mode_active is True
    assert store.get_safe_mode().active is True
    assert len(stack.alerts.alerts) == 1
    alert = stack.alerts.alerts[0]
    assert alert.severity == "CRITICAL"
    assert len(store.list_positions(open_only=True)) == 0  # never adopted

    with pytest.raises(SafeModeViolation):
        service.submit(make_intent())
    client.close()
