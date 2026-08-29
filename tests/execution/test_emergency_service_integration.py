"""ExecutionService + EmergencyController integration DoD tests.

Proves the emergency controls gate the real submit path, feed the dead man
switch from the heartbeat stream, and that the EMERGENCY_KILL side effects
(cancel pending, optional flatten) run end-to-end through the service —
independently of any strategy or LLM process.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from adapters.mt4.protocol import HeartbeatEvent
from core.domain.enums import EmergencyLevel, OrderSide, OrderState, OrderType, PositionSide
from core.schemas.execution import ExecutionPosition
from engines.execution.emergency import (
    EMERGENCY_STRATEGY_ID,
    EmergencyController,
    EmergencyControlViolation,
    EmergencyPolicy,
)
from engines.execution.live_gate import LiveGateViolation

from execution_helpers import FakeReconcileClient, Stack, make_intent


def heartbeat(t: datetime) -> HeartbeatEvent:
    return HeartbeatEvent(
        message_id=uuid4(),
        timestamp=t,
        sequence=0,
        broker_connected=True,
        trading_enabled=True,
        mode="PAPER",
    )


def pending_order(stack: Stack) -> None:
    intent = make_intent()
    stack.applier.record_order_intent(intent, venue="mt4")
    stack.applier.record_submitted(intent.order_intent_id)
    stack.applier.record_acknowledged(intent.order_intent_id, venue_order_id="ord-1")


# ── Entry gating on the real submit path ─────────────────────────────────
def test_submit_blocked_by_strategy_kill() -> None:
    stack = Stack()
    stack.emergency.activate(
        EmergencyLevel.STRATEGY_KILL, target="strategy-A", actor="ops", reason="rogue"
    )
    client = FakeReconcileClient()
    service = stack.service(client)
    with pytest.raises(EmergencyControlViolation):
        service.submit(make_intent())
    assert client.submitted == []  # never reached the wire


def test_submit_blocked_by_instrument_kill() -> None:
    stack = Stack()
    stack.emergency.activate(
        EmergencyLevel.INSTRUMENT_KILL, target="EURUSD", actor="ops", reason="no liquidity"
    )
    client = FakeReconcileClient()
    service = stack.service(client)
    with pytest.raises(EmergencyControlViolation):
        service.submit(make_intent())
    assert client.submitted == []


def test_submit_blocked_by_no_new_positions() -> None:
    stack = Stack()
    stack.emergency.activate(EmergencyLevel.NO_NEW_POSITIONS, actor="ops", reason="risk event")
    client = FakeReconcileClient()
    service = stack.service(client)
    with pytest.raises(EmergencyControlViolation):
        service.submit(make_intent())
    assert client.submitted == []


def test_submit_blocked_by_dead_man_safe_state() -> None:
    stack = Stack(policy=EmergencyPolicy(heartbeat_timeout=timedelta(seconds=6)))
    client = FakeReconcileClient()
    service = stack.service(client)
    stack.clock.advance(timedelta(seconds=7))
    with pytest.raises(EmergencyControlViolation):
        service.submit(make_intent())  # check_emergency engages the DMS first
    assert stack.emergency.safe_execution_state_active() is True
    assert client.submitted == []


def test_heartbeat_stream_keeps_submit_allowed_and_restores_after_loss() -> None:
    stack = Stack(policy=EmergencyPolicy(heartbeat_timeout=timedelta(seconds=6)))
    client = FakeReconcileClient()
    service = stack.service(client)
    # Heartbeat flows through the event pump into the dead man switch.
    client.events = [heartbeat(stack.clock.now())]
    service.drain_events()
    stack.clock.advance(timedelta(seconds=5))
    assert service.submit(make_intent()).state is OrderState.ACKNOWLEDGED

    # Loss → safe state; next submit blocked without any broker action.
    stack.clock.advance(timedelta(seconds=7))
    with pytest.raises(EmergencyControlViolation):
        service.submit(make_intent())
    assert len(client.submitted) == 1

    # Recovery heartbeat clears the safe state.
    client.events = [heartbeat(stack.clock.now())]
    service.drain_events()
    assert stack.emergency.safe_execution_state_active() is False


# ── EMERGENCY_KILL side effects through the service ──────────────────────
def test_emergency_kill_cancels_pending_orders_through_service() -> None:
    stack = Stack()
    pending_order(stack)
    client = FakeReconcileClient()
    service = stack.service(client)
    controller = EmergencyController(
        stack.emergency_store,
        stack.clock,
        policy=EmergencyPolicy(),
        audit=stack.audit,
        events=stack.events,
        alerts=stack.alerts,
        pending_canceller=service.cancel_pending_orders,
    )
    controller.activate(EmergencyLevel.EMERGENCY_KILL, actor="ops", reason="test")
    assert len(client.cancelled) == 1
    record = next(iter(stack.store.list_orders()))
    assert record.state is OrderState.CANCELLED


def test_emergency_kill_flattens_positions_through_service() -> None:
    stack = Stack()
    client = FakeReconcileClient()
    service = stack.service(client)
    # One open position exists at the venue + persisted locally.
    stack.store.upsert_position(
        ExecutionPosition(
            venue_position_id="pos-1",
            account_id="acct-1",
            instrument_id="EURUSD",
            side=PositionSide.LONG,
            quantity=Decimal("0.10"),
            average_entry_price=Decimal("1.08000"),
            opened_at=stack.clock.now(),
            updated_at=stack.clock.now(),
        )
    )
    controller = EmergencyController(
        stack.emergency_store,
        stack.clock,
        policy=EmergencyPolicy(flatten_on_emergency_kill=True),
        audit=stack.audit,
        events=stack.events,
        alerts=stack.alerts,
        flattener=service.flatten_positions,
    )
    controller.activate(EmergencyLevel.EMERGENCY_KILL, actor="ops", reason="test")
    assert len(client.submitted) == 1
    closing = client.submitted[0]
    assert closing["strategy_id"] == EMERGENCY_STRATEGY_ID
    assert closing["order_type"] is OrderType.MARKET
    assert closing["side"] is OrderSide.SELL  # offsetting the LONG position
    assert closing["quantity"] == Decimal("0.10")


def test_flatten_refused_without_active_emergency() -> None:
    stack = Stack()
    client = FakeReconcileClient()
    service = stack.service(client)
    with pytest.raises(LiveGateViolation):
        service.flatten_positions(reason="not authorized")
    assert client.submitted == []


def test_cancel_pending_refused_without_emergency_kill() -> None:
    stack = Stack()
    client = FakeReconcileClient()
    service = stack.service(client)
    with pytest.raises(LiveGateViolation):
        service.cancel_pending_orders(reason="not authorized")
    assert client.cancelled == []


def test_no_heartbeat_and_pending_orders_are_untouched_on_connectivity_loss() -> None:
    """INV-7: connectivity loss never cancels or flattens — only blocks entries."""
    stack = Stack(policy=EmergencyPolicy(heartbeat_timeout=timedelta(seconds=6)))
    pending_order(stack)
    client = FakeReconcileClient()
    service = stack.service(client)
    stack.clock.advance(timedelta(seconds=7))
    with pytest.raises(EmergencyControlViolation):
        service.submit(make_intent())
    assert client.cancelled == []
    assert client.submitted == []
    # The previously pending order still shows live state — SL/TP untouched.
    record = next(iter(stack.store.list_orders()))
    assert record.state is OrderState.ACKNOWLEDGED
