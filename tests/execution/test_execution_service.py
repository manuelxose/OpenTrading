"""ExecutionService DoD tests: the 7-step startup reconciliation and the
write-before-send submit path with a protocol-level fake client."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from adapters.mt4.errors import Mt4ProtocolError
from core.domain.enums import OrderState, PositionSide
from core.observability.metrics import OperationalMetrics
from engines.execution.applier import ExecutionDivergenceError
from engines.execution.safe_mode import SafeModeViolation
from engines.execution.service import ExecutionService
from prometheus_client import CollectorRegistry, generate_latest

from execution_helpers import (
    FakeReconcileClient,
    Stack,
    get_order,
    make_fill_event,
    make_intent,
    make_position_snapshot_event,
    make_reconciliation_response,
    make_reject,
    not_connected_error,
)


@pytest.fixture()
def stack() -> Stack:
    return Stack()


def _service(
    stack: Stack,
    client: FakeReconcileClient,
    operational_metrics: OperationalMetrics | None = None,
) -> ExecutionService:
    return ExecutionService(
        store=stack.store,
        applier=stack.applier,
        reconciler=stack.reconciler,
        controller=stack.controller,
        client=client,
        clock=stack.clock,
        audit=stack.audit,
        events=stack.events,
        operational_metrics=operational_metrics,
    )


def test_clean_startup_reconciles_and_resyncs(stack: Stack) -> None:
    client = FakeReconcileClient()
    client.responses = [
        make_reconciliation_response(stack.clock.now(), last_sequences={"strategy-A": 7, "CORE": 2})
    ]
    service = _service(stack, client)
    outcome = service.startup_reconciliation()
    assert outcome.broker_reachable is True
    assert outcome.safe_mode_active is False
    assert outcome.material_discrepancies == 0
    assert client.resynced == [{"strategy-A": 7, "CORE": 2}]
    runs = stack.store.list_reconciliation_runs()
    assert len(runs) == 1
    assert runs[0].safe_mode_exited is False
    assert any(e.event_name == "order.reconciled" for e in stack.events.events)


def test_unreachable_broker_enters_safe_mode_with_alert(stack: Stack) -> None:
    client = FakeReconcileClient()
    client.errors = [not_connected_error()]
    service = _service(stack, client)
    outcome = service.startup_reconciliation()
    assert outcome.broker_reachable is False
    assert outcome.safe_mode_active is True
    assert "BROKER_UNREACHABLE" in outcome.safe_mode_reason_codes
    assert outcome.material_discrepancies == 1
    assert stack.store.get_safe_mode().active is True
    assert len(stack.alerts.alerts) == 1
    assert any(e.event_name == "reconciliation.divergence" for e in stack.events.events)
    runs = stack.store.list_reconciliation_runs()
    assert runs[0].broker_reachable is False


def test_clean_run_after_partition_exits_safe_mode(stack: Stack) -> None:
    stack.controller.enter(["BROKER_UNREACHABLE"], note="earlier partition")
    client = FakeReconcileClient()
    client.responses = [make_reconciliation_response(stack.clock.now())]
    service = _service(stack, client)
    outcome = service.startup_reconciliation()
    assert outcome.safe_mode_active is False
    assert stack.store.get_safe_mode().active is False
    runs = stack.store.list_reconciliation_runs()
    assert runs[-1].safe_mode_exited is True


def test_material_divergence_enters_safe_mode(stack: Stack) -> None:
    intent = make_intent()
    stack.applier.record_order_intent(intent, venue="mt4")
    stack.applier.record_submitted(intent.order_intent_id)
    stack.applier.record_acknowledged(intent.order_intent_id, venue_order_id="ord-1")
    client = FakeReconcileClient()
    client.responses = [make_reconciliation_response(stack.clock.now())]  # venue silent
    service = _service(stack, client)
    outcome = service.startup_reconciliation()
    assert outcome.safe_mode_active is True
    assert outcome.material_discrepancies >= 1
    assert stack.store.get_safe_mode().active is True
    assert any(e.event_name == "reconciliation.divergence" for e in stack.events.events)


def test_submit_persists_before_send_and_applies_reply(stack: Stack) -> None:
    client = FakeReconcileClient()
    intent = make_intent()
    client.events = [
        make_fill_event(stack.clock.now(), intent.order_intent_id, quantity=Decimal("0.10"))
    ]
    service = _service(stack, client)
    record = service.submit(intent)
    assert record.state is OrderState.FILLED
    assert record.filled_quantity == intent.quantity
    assert record.submitted_at is not None
    assert record.acknowledged_at is not None
    assert record.filled_at is not None
    assert len(client.submitted) == 1


def test_duplicate_fill_is_counted_once_and_restart_uses_persisted_submit_time(
    stack: Stack,
) -> None:
    registry = CollectorRegistry()
    operational_metrics = OperationalMetrics(registry=registry)
    intent = make_intent()
    stack.applier.record_order_intent(intent, venue="mt4")
    stack.applier.record_submitted(intent.order_intent_id)
    stack.applier.record_acknowledged(intent.order_intent_id, venue_order_id="ord-1")
    stack.clock.advance(timedelta(seconds=2))
    event = make_fill_event(stack.clock.now(), intent.order_intent_id, quantity=Decimal("0.10"))
    client = FakeReconcileClient()
    client.events = [event, event]

    restarted_service = _service(stack, client, operational_metrics)
    restarted_service.drain_events()

    body = generate_latest(registry).decode()
    assert 'opentrading_execution_outcomes_total{outcome="filled"} 1.0' in body
    assert 'opentrading_execution_latency_seconds_sum{outcome="filled"} 2.0' in body


def test_submit_with_reject_reply_records_rejection(stack: Stack) -> None:
    client = FakeReconcileClient()
    intent = make_intent()
    client.submit_reply = make_reject(intent.order_intent_id, "INSUFFICIENT_MARGIN")
    service = _service(stack, client)
    record = service.submit(intent)
    assert record.state is OrderState.REJECTED
    assert record.reject_reason == "INSUFFICIENT_MARGIN"


def test_submit_blocked_in_safe_mode(stack: Stack) -> None:
    stack.controller.enter(["RECONCILIATION_DIVERGENCE"])
    client = FakeReconcileClient()
    service = _service(stack, client)
    with pytest.raises(SafeModeViolation):
        service.submit(make_intent())
    assert client.submitted == []  # nothing ever reached the wire


def test_crash_after_submit_leaves_authoritative_state(stack: Stack) -> None:
    """send_order() raised — the SUBMITTED record survives the 'crash' and the
    next startup closes it deterministically (no venue evidence)."""
    client = FakeReconcileClient()
    client.submit_error = not_connected_error()
    intent = make_intent()
    service = _service(stack, client)
    with pytest.raises(Mt4ProtocolError):
        service.submit(intent)
    record = get_order(stack.store, intent.order_intent_id)
    assert record.state is OrderState.SUBMITTED  # persisted before the send

    # "Restart": a fresh client sees an empty venue — explainable closure.
    restarted = Stack(store=stack.store, clock=stack.clock)
    client2 = FakeReconcileClient()
    client2.responses = [make_reconciliation_response(stack.clock.now())]
    service2 = _service(restarted, client2)
    outcome = service2.startup_reconciliation()
    assert outcome.safe_mode_active is False
    assert get_order(stack.store, intent.order_intent_id).state is OrderState.RECONCILED


def test_duplicate_fill_with_distinct_ids_escalates_to_safe_mode(stack: Stack) -> None:
    """Two genuinely distinct full-size fills exceed requested → SAFE_MODE."""
    intent = make_intent()
    stack.applier.record_order_intent(intent, venue="mt4")
    stack.applier.record_submitted(intent.order_intent_id)
    stack.applier.record_acknowledged(intent.order_intent_id, venue_order_id="ord-1")
    client = FakeReconcileClient()
    client.events = [
        make_fill_event(
            stack.clock.now(), intent.order_intent_id, quantity=Decimal("0.10"), sequence=1
        ),
        make_fill_event(
            stack.clock.now(), intent.order_intent_id, quantity=Decimal("0.10"), sequence=2
        ),
    ]
    service = _service(stack, client)
    with pytest.raises(ExecutionDivergenceError):
        service.drain_events()
    assert stack.store.get_safe_mode().active is True
    assert "OVERFILL_DETECTED" in stack.store.get_safe_mode().reason_codes
    assert len(stack.alerts.alerts) == 1
    # Authoritative state: exactly one fill applied.
    assert get_order(stack.store, intent.order_intent_id).filled_quantity == Decimal("0.10")


def test_position_snapshot_event_persists_positions(stack: Stack) -> None:
    intent = make_intent()
    stack.applier.record_order_intent(intent, venue="mt4")
    stack.applier.record_submitted(intent.order_intent_id)
    stack.applier.record_acknowledged(intent.order_intent_id, venue_order_id="ord-1")
    stack.applier.record_fill(
        intent.order_intent_id,
        event_id="fill-1",
        sequence=1,
        filled_quantity=intent.quantity,
        average_fill_price=Decimal("1.08000"),
    )
    client = FakeReconcileClient()
    client.events = [
        make_position_snapshot_event(stack.clock.now(), intent_id=intent.order_intent_id)
    ]
    service = _service(stack, client)
    service.drain_events()
    positions = stack.store.list_positions(open_only=True)
    assert len(positions) == 1
    assert positions[0].venue_position_id == "pos-1"
    assert positions[0].order_intent_id == intent.order_intent_id
    assert positions[0].side is PositionSide.LONG
    assert positions[0].quantity == intent.quantity


def test_startup_outcome_carries_run_identity(stack: Stack) -> None:
    client = FakeReconcileClient()
    client.responses = [make_reconciliation_response(stack.clock.now())]
    service = _service(stack, client)
    outcome = service.startup_reconciliation()
    assert outcome.run_id == stack.store.list_reconciliation_runs()[-1].run_id


def test_unknown_intent_in_store_is_an_error(stack: Stack) -> None:
    with pytest.raises(ValueError, match="unknown order_intent_id"):
        stack.applier.record_acknowledged(UUID("00000000-0000-0000-0000-000000000001"))
