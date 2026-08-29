"""Broker event chaos: partial fills and malformed event streams.

Wire-level (real ZeroMQ loopback against the MT4 emulator):

- a market order partially filled at the venue completes on the next quote
  without duplicates, overfill or safe mode;
- the Core crashes after the partial fill and the remainder fills while it is
  down: startup reconciliation flags the quantity divergence as MATERIAL and
  enters SAFE_MODE (new entries blocked, nothing adopted or auto-closed).

Service-boundary (deterministic, no sockets):

- a duplicate broker fill is counted exactly once (fingerprint dedupe);
- out-of-order events (fill for a later sequence first, reject after fill)
  resolve to the same correct state without corruption or safe mode.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from decimal import Decimal
from uuid import uuid4

import pytest
from adapters.mt4.broker import BrokerConfig, SymbolSpec
from adapters.mt4.client import Mt4ExecutionClient
from adapters.mt4.emulator import Mt4Emulator
from adapters.mt4.protocol import (
    FillEvent,
    Mt4MessageType,
    PartialFillEvent,
    WireMessage,
)
from adapters.mt4.transport import ConnectionHealth, Mt4Endpoints
from core.clock.clocks import SystemClock
from core.domain.enums import OrderState
from core.schemas.trading import OrderIntent
from engines.execution.persistence import InMemoryExecutionStateStore
from engines.execution.safe_mode import SafeModeViolation
from engines.execution.service import ExecutionService

from execution_helpers import (
    FakeReconcileClient,
    Stack,
    get_order,
    make_ack,
    make_fill_event,
    make_intent,
    make_position_snapshot_event,
    make_reject,
    new_clock,
)

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
        store=store,
        applier=stack.applier,
        reconciler=stack.reconciler,
        controller=stack.controller,
        client=client,
        clock=stack.clock,
        audit=stack.audit,
        events=stack.events,
    )


class _RecordingClient:
    """Captures every wire event the service drains — including the ones
    applied inside ``submit`` itself."""

    def __init__(self, inner: Mt4ExecutionClient) -> None:
        self._inner = inner
        self.seen: list[WireMessage] = []

    def __getattr__(self, name: str):
        attr = getattr(self._inner, name)
        if name != "drain_events":
            return attr

        def drain(*args: object, **kwargs: object) -> list[WireMessage]:
            drained = attr(*args, **kwargs)
            self.seen.extend(drained)
            return drained

        return drain


def _service_with_client(
) -> tuple[InMemoryExecutionStateStore, Stack, FakeReconcileClient, ExecutionService]:
    store = InMemoryExecutionStateStore()
    stack = Stack(store=store, clock=new_clock())
    client = FakeReconcileClient()
    return store, stack, client, stack.service(client)


def _drain_until(
    service: ExecutionService, intent: OrderIntent, state: OrderState, *, seconds: float = 6.0
) -> list[WireMessage]:
    seen: list[WireMessage] = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        seen.extend(service.drain_events(timeout_ms=50))
        order = service._store.get_order(intent.order_intent_id)
        if order is not None and order.state is state:
            return seen
    raise TimeoutError(f"order never reached {state.value}")


@pytest.fixture()
def partial_emulator() -> Iterator[Mt4Emulator]:
    emu = Mt4Emulator(
        SystemClock(),
        endpoints=Mt4Endpoints(
            command_addr="tcp://127.0.0.1:*",
            events_addr="tcp://127.0.0.1:*",
            quotes_addr="tcp://127.0.0.1:*",
        ),
        broker_config=BrokerConfig(
            symbols={"EURUSD": EURUSD}, partial_fill_ratio=Decimal("0.5")
        ),
        seed=19,
        heartbeat_interval_seconds=0.1,
        quote_interval_seconds=0.05,
    )
    emu.start()
    yield emu
    emu.stop()


@pytest.fixture()
def slow_quotes_emulator() -> Iterator[Mt4Emulator]:
    """Partial fills stay observable: the remainder only fills on a later
    market step, and quotes advance every 60s unless driven manually."""
    emu = Mt4Emulator(
        SystemClock(),
        endpoints=Mt4Endpoints(
            command_addr="tcp://127.0.0.1:*",
            events_addr="tcp://127.0.0.1:*",
            quotes_addr="tcp://127.0.0.1:*",
        ),
        broker_config=BrokerConfig(
            symbols={"EURUSD": EURUSD}, partial_fill_ratio=Decimal("0.5")
        ),
        seed=19,
        heartbeat_interval_seconds=0.1,
        quote_interval_seconds=60.0,
    )
    emu.start()
    yield emu
    emu.stop()


class TestWireLevelPartialFills:
    def test_partial_fill_completes_without_duplicates_or_safe_mode(
        self, partial_emulator: Mt4Emulator
    ) -> None:
        store = InMemoryExecutionStateStore()
        recorder = _RecordingClient(_connect(partial_emulator))
        service = _service(store, recorder)  # type: ignore[arg-type]
        intent = make_intent(quantity=Decimal("0.10"))

        record = service.submit(intent)
        _drain_until(service, intent, OrderState.FILLED)

        # The wire carried a real partial fill before the remainder completed.
        assert any(isinstance(event, PartialFillEvent) for event in recorder.seen)
        filled = get_order(store, intent.order_intent_id)
        assert filled.state is OrderState.FILLED
        assert filled.filled_quantity == intent.quantity  # exact, no overfill
        assert len(store.list_orders()) == 1  # no duplicate orders
        positions = store.list_positions(open_only=True)
        assert len(positions) == 1
        assert positions[0].quantity == intent.quantity
        assert store.get_safe_mode().active is False
        assert record.state is OrderState.FILLED
        recorder._inner.close()

    def test_crash_after_partial_fill_flags_divergence_and_blocks_entries(
        self, slow_quotes_emulator: Mt4Emulator
    ) -> None:
        store = InMemoryExecutionStateStore()
        client = _connect(slow_quotes_emulator)
        service = _service(store, client)
        intent = make_intent(quantity=Decimal("0.10"))

        # The venue partially fills (0.05); quotes advance slowly, so the
        # remainder is deterministically still working at the venue.
        service.submit(intent)
        partial = get_order(store, intent.order_intent_id)
        assert partial.state is OrderState.PARTIALLY_FILLED
        assert partial.filled_quantity == Decimal("0.05")

        # Core crash: the venue completes the remainder while nothing
        # listens — the fill events are lost with the process.
        client.close()
        slow_quotes_emulator.broker.advance()

        # Restart: the broker position (0.10) disagrees with the persisted
        # fill (0.05) — an unexplained MATERIAL divergence → SAFE_MODE.
        restarted_client = _connect(slow_quotes_emulator)
        restarted_service = _service(store, restarted_client)
        outcome = restarted_service.startup_reconciliation()
        assert outcome.material_discrepancies >= 1
        assert outcome.safe_mode_active is True
        assert store.get_safe_mode().active is True
        assert "RECONCILIATION_DIVERGENCE" in store.get_safe_mode().reason_codes

        # No uncontrolled exposure: new entries are blocked and the platform
        # never auto-adopts or auto-closes the divergent position.
        with pytest.raises(SafeModeViolation):
            restarted_service.submit(make_intent())
        positions = store.list_positions(open_only=True)
        assert len(positions) == 1
        assert positions[0].quantity == Decimal("0.05")  # unchanged, not adopted
        restarted_client.close()


class TestBrokerEventStreamIntegrity:
    def test_duplicate_broker_fill_is_counted_exactly_once(self) -> None:
        store, stack, client, service = _service_with_client()
        intent = make_intent()
        now = stack.clock.now()
        fill = make_fill_event(now, intent.order_intent_id, quantity=intent.quantity)
        client.submit_reply = make_ack(intent.order_intent_id)
        client.events = [
            fill,
            fill.model_copy(deep=True),  # identical message_id + sequence
            make_position_snapshot_event(now, intent_id=intent.order_intent_id),
        ]

        record = service.submit(intent)
        assert record.state is OrderState.FILLED
        assert record.filled_quantity == intent.quantity  # not double-counted
        assert record.version == 4  # intent → submitted → ack → one fill only
        assert len(store.list_positions(open_only=True)) == 1
        assert store.get_safe_mode().active is False

    def test_out_of_order_events_resolve_to_correct_state(self) -> None:
        store, stack, client, service = _service_with_client()
        intent = make_intent()
        now = stack.clock.now()
        later_sequence = make_fill_event(
            now, intent.order_intent_id, quantity=Decimal("0.05"), sequence=2
        )
        earlier_sequence = PartialFillEvent(
            message_id=uuid4(),
            timestamp=now,
            sequence=1,
            order_intent_id=intent.order_intent_id,
            venue_order_id="ord-1",
            filled_quantity=Decimal("0.05"),
            remaining_quantity=Decimal("0.05"),
            average_fill_price=Decimal("1.08000"),
            symbol="EURUSD",
        )
        stale_reject = make_reject(intent.order_intent_id, "MARKET_CLOSED")
        client.submit_reply = make_ack(intent.order_intent_id)
        # The broker delivers the later sequence first, then the earlier one,
        # then a reject that lost the race with the fill.
        client.events = [later_sequence, earlier_sequence, stale_reject]

        record = service.submit(intent)
        assert record.state is OrderState.FILLED
        assert record.filled_quantity == intent.quantity  # 0.05 + 0.05, once each
        assert record.last_event_sequence == 2
        assert len(store.list_orders()) == 1
        assert store.get_safe_mode().active is False

    def test_fill_for_unknown_intent_is_skipped_without_divergence(self) -> None:
        store, stack, client, service = _service_with_client()
        intent = make_intent()
        now = stack.clock.now()
        # A broker event the platform cannot attribute (stale/unknown frame).
        unknown = make_fill_event(now, uuid4(), quantity=Decimal("0.10"))
        fill = make_fill_event(now, intent.order_intent_id, quantity=intent.quantity)
        client.submit_reply = make_ack(intent.order_intent_id)
        client.events = [unknown, fill]

        record = service.submit(intent)
        assert record.state is OrderState.FILLED
        assert store.get_safe_mode().active is False
        assert any(
            entry.action == "execution.event.skipped" for entry in stack.audit_sink.entries
        )


class TestNoDuplicateFillFingerprint:
    def test_fill_event_ids_are_sequence_scoped(self) -> None:
        """Two fills sharing a message_id but different sequences must both
        apply (they are distinct broker events), while an exact fingerprint
        replay never double-counts."""
        store, stack, client, service = _service_with_client()
        intent = make_intent()
        now = stack.clock.now()
        first = make_fill_event(
            now, intent.order_intent_id, quantity=Decimal("0.05"), sequence=1
        )
        second = FillEvent(
            message_id=first.message_id,  # same frame id, next sequence
            timestamp=now,
            sequence=2,
            order_intent_id=intent.order_intent_id,
            venue_order_id="ord-1",
            filled_quantity=Decimal("0.05"),
            average_fill_price=Decimal("1.08000"),
            symbol="EURUSD",
            side=first.side,
        )
        replay = first.model_copy(deep=True)  # exact duplicate of sequence 1
        client.submit_reply = make_ack(intent.order_intent_id)
        client.events = [first, second, replay]

        record = service.submit(intent)
        assert record.state is OrderState.FILLED
        assert record.filled_quantity == intent.quantity  # 0.05 + 0.05, replay ignored
        assert store.get_safe_mode().active is False
