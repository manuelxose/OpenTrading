"""Chaos DoD: the platform restarts at any point of the order lifecycle without
losing authoritative state (INV-6).

Real ZeroMQ loopback against the Python MT4 emulator — no MetaTrader required:

- crash after submit (broker never saw the order)  → explainable closure;
- crash before ACK (broker filled, events lost)     → healed to FILLED from the
  broker position at startup reconciliation;
- MT4 restart                                        → resync + clean re-entry;
- duplicate fill / out-of-order events               → covered deterministically
  in ``tests/execution`` (fingerprint dedupe, fill-before-ACK, overfill).
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
from core.domain.enums import OrderState
from engines.execution.persistence import InMemoryExecutionStateStore
from engines.execution.service import ExecutionService

from execution_helpers import Stack, get_order, make_intent

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
        seed=11,
        heartbeat_interval_seconds=0.1,
        quote_interval_seconds=0.05,
    )
    emu.start()
    yield emu
    emu.stop()


def _connect(emulator: Mt4Emulator, *, timeout: float = 2.0) -> Mt4ExecutionClient:
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


def test_crash_before_ack_is_healed_from_broker_position(emulator: Mt4Emulator) -> None:
    """The service died right after the wire send: ACK and fill events never
    reached the store, but the broker already opened the position."""
    store = InMemoryExecutionStateStore()
    stack = Stack(store=store, clock=SystemClock())
    intent = make_intent()
    # What the service persisted before the send (write-before-send contract):
    stack.applier.record_order_intent(intent, venue="mt4")
    stack.applier.record_submitted(intent.order_intent_id)

    client = _connect(emulator)
    reply = client.submit_order(
        order_intent_id=intent.order_intent_id,
        strategy_id=intent.strategy_id,
        strategy_version=intent.strategy_version,
        symbol=intent.instrument_id,
        side=intent.side,
        quantity=intent.quantity,
        order_type=intent.order_type,
        max_slippage=intent.max_slippage,
    )
    assert reply is not None  # broker filled; events below were never applied
    time.sleep(0.3)  # let the broker advance and fill
    client.close()  # queued events are lost — the "crash"

    # Restart: a fresh client + service reconcile against the live broker.
    restarted_client = _connect(emulator)
    service = _service(store, restarted_client)
    outcome = service.startup_reconciliation()
    assert outcome.broker_reachable is True
    assert outcome.safe_mode_active is False
    record = get_order(store, intent.order_intent_id)
    assert record.state is OrderState.FILLED
    assert record.venue_position_id is not None
    positions = store.list_positions(open_only=True)
    assert len(positions) == 1
    assert positions[0].order_intent_id == intent.order_intent_id
    restarted_client.close()


def test_crash_after_submit_broker_never_saw_is_closed_explainably(
    emulator: Mt4Emulator,
) -> None:
    """SUBMITTED was persisted, the wire send never happened (crash): the venue
    has no trace, so reconciliation closes the order deterministically."""
    store = InMemoryExecutionStateStore()
    stack = Stack(store=store, clock=SystemClock())
    intent = make_intent()
    stack.applier.record_order_intent(intent, venue="mt4")
    stack.applier.record_submitted(intent.order_intent_id)
    # No send at all — the crash happened before the socket write.

    client = _connect(emulator)
    service = _service(store, client)
    outcome = service.startup_reconciliation()
    assert outcome.safe_mode_active is False
    assert outcome.material_discrepancies == 0
    record = get_order(store, intent.order_intent_id)
    assert record.state is OrderState.RECONCILED
    assert record.cancelled_at is not None
    client.close()


def test_mt4_restart_resyncs_and_reenters(emulator: Mt4Emulator) -> None:
    """The bridge restarts (transport dies, broker state survives): the service
    resyncs sequence namespaces and a new order executes cleanly."""
    store = InMemoryExecutionStateStore()
    client = _connect(emulator)
    service = _service(store, client)

    first = make_intent()
    record = service.submit(first)
    assert record.state is OrderState.FILLED

    client.close()
    emulator.stop()  # MT4 restart: sockets die, broker + gate state survive
    emulator.start()

    restarted_client = _connect(emulator)
    restarted_service = _service(store, restarted_client)
    outcome = restarted_service.startup_reconciliation()
    assert outcome.safe_mode_active is False
    assert get_order(store, first.order_intent_id).state is OrderState.RECONCILED

    second = make_intent(strategy_id=first.strategy_id)
    second_record = restarted_service.submit(second)
    assert second_record.state is OrderState.FILLED
    assert get_order(store, second.order_intent_id).state is OrderState.FILLED
    restarted_client.close()


def test_same_intent_resubmitted_after_crash_is_one_trade(emulator: Mt4Emulator) -> None:
    """Idempotency through the whole stack: resubmitting the identical intent
    after a 'crash' must not open a second position (Phase 6 invariant)."""
    store = InMemoryExecutionStateStore()
    stack = Stack(store=store, clock=SystemClock())
    intent = make_intent()
    stack.applier.record_order_intent(intent, venue="mt4")
    stack.applier.record_submitted(intent.order_intent_id)

    client = _connect(emulator)
    reply = client.submit_order(
        order_intent_id=intent.order_intent_id,
        strategy_id=intent.strategy_id,
        strategy_version=intent.strategy_version,
        symbol=intent.instrument_id,
        side=intent.side,
        quantity=intent.quantity,
        order_type=intent.order_type,
        max_slippage=intent.max_slippage,
    )
    assert reply is not None
    time.sleep(0.3)
    client.close()

    restarted_client = _connect(emulator)
    service = _service(store, restarted_client)
    assert service.startup_reconciliation().safe_mode_active is False
    # The healed order is FILLED; resubmitting the same intent is a broker-side
    # replay (idempotency ledger) that must not create a second position.
    replay = restarted_client.submit_order(
        order_intent_id=intent.order_intent_id,
        strategy_id=intent.strategy_id,
        strategy_version=intent.strategy_version,
        symbol=intent.instrument_id,
        side=intent.side,
        quantity=intent.quantity,
        order_type=intent.order_type,
        max_slippage=intent.max_slippage,
    )
    assert replay is not None
    time.sleep(0.3)
    restarted_client.close()

    final_client = _connect(emulator)
    final_service = _service(store, final_client)
    final_service.startup_reconciliation()
    assert len(store.list_positions(open_only=True)) == 1  # one trade, never two
    final_client.close()
