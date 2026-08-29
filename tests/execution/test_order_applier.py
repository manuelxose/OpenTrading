"""OrderStateApplier DoD tests: full canonical lifecycle, crash-restart state,
duplicate fills, out-of-order events, and overfill divergence."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from core.domain.enums import DiscrepancyCode, OrderState
from core.domain.state_machines import InvalidStateTransition
from engines.execution.applier import ExecutionDivergenceError

from execution_helpers import Stack, get_order, make_intent


@pytest.fixture()
def stack() -> Stack:
    return Stack()


def _candidate(stack: Stack):
    intent = make_intent()
    stack.applier.record_candidate(
        order_intent_id=intent.order_intent_id,
        strategy_id=intent.strategy_id,
        strategy_version=intent.strategy_version,
        instrument_id=intent.instrument_id,
        side=intent.side,
        order_type=intent.order_type,
        requested_quantity=intent.quantity,
    )
    return intent


def test_full_canonical_lifecycle(stack: Stack) -> None:
    intent = _candidate(stack)
    assert stack.applier.record_approved(intent.order_intent_id).state is OrderState.APPROVED
    assert stack.applier.record_order_intent(intent, venue="mt4").state is OrderState.ORDER_INTENT
    assert stack.applier.record_submitted(intent.order_intent_id).state is OrderState.SUBMITTED
    acknowledged = stack.applier.record_acknowledged(
        intent.order_intent_id, venue_order_id="ord-1", event_id="ack-1"
    )
    assert acknowledged.state is OrderState.ACKNOWLEDGED
    assert acknowledged.venue_order_id == "ord-1"

    partial = stack.applier.record_partial_fill(
        intent.order_intent_id,
        event_id="fill-1",
        sequence=2,
        filled_quantity=Decimal("0.04"),
        average_fill_price=Decimal("1.08001"),
        venue_order_id="ord-1",
    )
    assert partial.state is OrderState.PARTIALLY_FILLED
    assert partial.filled_quantity == Decimal("0.04")
    assert partial.remaining_quantity == Decimal("0.06")

    filled = stack.applier.record_fill(
        intent.order_intent_id,
        event_id="fill-2",
        sequence=3,
        filled_quantity=Decimal("0.06"),
        average_fill_price=Decimal("1.08002"),
        venue_order_id="ord-1",
        venue_position_id="pos-1",
    )
    assert filled.state is OrderState.FILLED
    assert filled.filled_quantity == intent.quantity
    assert filled.remaining_quantity == 0
    assert filled.venue_position_id == "pos-1"
    assert filled.filled_at is not None
    assert filled.average_fill_price == Decimal("1.080016")

    reconciled = stack.applier.mark_reconciled(intent.order_intent_id, note="clean")
    assert reconciled.state is OrderState.RECONCILED
    closed = stack.applier.record_closed(intent.order_intent_id)
    assert closed.state is OrderState.CLOSED
    reviewed = stack.applier.record_reviewed(intent.order_intent_id)
    assert reviewed.state is OrderState.REVIEWED
    assert reviewed.version == 10  # nine transitions after creation


def test_risk_rejected_path_terminates(stack: Stack) -> None:
    intent = _candidate(stack)
    rejected = stack.applier.record_risk_rejected(intent.order_intent_id, "RISK_LIMIT_EXCEEDED")
    assert rejected.state is OrderState.RISK_REJECTED
    assert rejected.reject_reason == "RISK_LIMIT_EXCEEDED"
    with pytest.raises(InvalidStateTransition):
        stack.applier.record_approved(intent.order_intent_id)


def test_fill_before_ack_synthesizes_acknowledged(stack: Stack) -> None:
    intent = make_intent()
    stack.applier.record_order_intent(intent, venue="mt4")
    stack.applier.record_submitted(intent.order_intent_id)
    filled = stack.applier.record_fill(
        intent.order_intent_id,
        event_id="fill-1",
        sequence=1,
        filled_quantity=intent.quantity,
        average_fill_price=Decimal("1.08000"),
        venue_order_id="ord-1",
    )
    assert filled.state is OrderState.FILLED
    assert filled.acknowledged_at is not None  # ACK synthesized atomically
    assert filled.filled_at is not None
    record = get_order(stack.store, intent.order_intent_id)
    assert record.state is OrderState.FILLED
    assert record.version == 4  # intent(1) submitted(2) ack-synth(3) filled(4)


def test_partial_fill_before_ack_synthesizes_acknowledged(stack: Stack) -> None:
    intent = make_intent()
    stack.applier.record_order_intent(intent, venue="mt4")
    stack.applier.record_submitted(intent.order_intent_id)
    partial = stack.applier.record_partial_fill(
        intent.order_intent_id,
        event_id="fill-1",
        sequence=1,
        filled_quantity=Decimal("0.05"),
        average_fill_price=Decimal("1.08000"),
    )
    assert partial.state is OrderState.PARTIALLY_FILLED
    assert partial.acknowledged_at is not None


def test_duplicate_fill_is_a_noop(stack: Stack) -> None:
    intent = make_intent()
    stack.applier.record_order_intent(intent, venue="mt4")
    stack.applier.record_submitted(intent.order_intent_id)
    stack.applier.record_acknowledged(intent.order_intent_id, venue_order_id="ord-1")
    filled = stack.applier.record_fill(
        intent.order_intent_id,
        event_id="fill-1",
        sequence=1,
        filled_quantity=intent.quantity,
        average_fill_price=Decimal("1.08000"),
    )
    duplicated = stack.applier.record_fill(
        intent.order_intent_id,
        event_id="fill-1",  # identical fingerprint
        sequence=1,
        filled_quantity=intent.quantity,
        average_fill_price=Decimal("1.08000"),
    )
    assert duplicated is filled
    assert duplicated.filled_quantity == intent.quantity
    assert duplicated.version == filled.version


def test_duplicate_ack_is_a_noop(stack: Stack) -> None:
    intent = make_intent()
    stack.applier.record_order_intent(intent, venue="mt4")
    stack.applier.record_submitted(intent.order_intent_id)
    first = stack.applier.record_acknowledged(
        intent.order_intent_id, venue_order_id="ord-1", event_id="ack-1"
    )
    second = stack.applier.record_acknowledged(
        intent.order_intent_id, venue_order_id="ord-1", event_id="ack-1"
    )
    assert second is first


def test_out_of_order_reject_and_ack_after_fill_are_noops(stack: Stack) -> None:
    intent = make_intent()
    stack.applier.record_order_intent(intent, venue="mt4")
    stack.applier.record_submitted(intent.order_intent_id)
    filled = stack.applier.record_fill(
        intent.order_intent_id,
        event_id="fill-1",
        sequence=1,
        filled_quantity=intent.quantity,
        average_fill_price=Decimal("1.08000"),
    )
    late_reject = stack.applier.record_rejected(
        intent.order_intent_id, reason="BROKER_ERROR", event_id="rej-1"
    )
    late_ack = stack.applier.record_acknowledged(
        intent.order_intent_id, venue_order_id="ord-1", event_id="ack-1"
    )
    assert late_reject is filled
    assert late_ack is filled
    assert get_order(stack.store, intent.order_intent_id).state is OrderState.FILLED


def test_reject_after_partial_fill_is_allowed(stack: Stack) -> None:
    intent = make_intent()
    stack.applier.record_order_intent(intent, venue="mt4")
    stack.applier.record_submitted(intent.order_intent_id)
    stack.applier.record_acknowledged(intent.order_intent_id, venue_order_id="ord-1")
    stack.applier.record_partial_fill(
        intent.order_intent_id,
        event_id="fill-1",
        sequence=1,
        filled_quantity=Decimal("0.04"),
        average_fill_price=Decimal("1.08000"),
    )
    rejected = stack.applier.record_rejected(
        intent.order_intent_id, reason="INSUFFICIENT_MARGIN", event_id="rej-1"
    )
    assert rejected.state is OrderState.REJECTED
    assert rejected.filled_quantity == Decimal("0.04")
    assert rejected.reject_reason == "INSUFFICIENT_MARGIN"


def test_overfill_divergence(stack: Stack) -> None:
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
    with pytest.raises(ExecutionDivergenceError) as exc_info:
        stack.applier.record_fill(
            intent.order_intent_id,
            event_id="fill-2",  # distinct event id — a genuine duplicate fill
            sequence=2,
            filled_quantity=intent.quantity,
            average_fill_price=Decimal("1.08000"),
        )
    assert exc_info.value.code is DiscrepancyCode.OVERFILL
    # Authoritative state is untouched by the failed attempt.
    assert get_order(stack.store, intent.order_intent_id).filled_quantity == intent.quantity


def test_fill_for_cancelled_order_diverges(stack: Stack) -> None:
    intent = make_intent()
    stack.applier.record_order_intent(intent, venue="mt4")
    stack.applier.record_submitted(intent.order_intent_id)
    stack.applier.record_cancelled(intent.order_intent_id, event_id="cancel-1")
    with pytest.raises(ExecutionDivergenceError) as exc_info:
        stack.applier.record_fill(
            intent.order_intent_id,
            event_id="fill-1",
            sequence=1,
            filled_quantity=intent.quantity,
            average_fill_price=Decimal("1.08000"),
        )
    assert exc_info.value.code is DiscrepancyCode.IDENTIFIER_MISMATCH


def test_cancel_after_submit_and_before_ack(stack: Stack) -> None:
    intent = make_intent()
    stack.applier.record_order_intent(intent, venue="mt4")
    stack.applier.record_submitted(intent.order_intent_id)
    cancelled = stack.applier.record_cancelled(intent.order_intent_id, event_id="cancel-1")
    assert cancelled.state is OrderState.CANCELLED
    assert cancelled.cancelled_at is not None


def test_invalid_transition_raises(stack: Stack) -> None:
    intent = make_intent()
    stack.applier.record_order_intent(intent, venue="mt4")
    with pytest.raises(InvalidStateTransition):
        stack.applier.record_fill(
            intent.order_intent_id,
            event_id="fill-1",
            sequence=1,
            filled_quantity=intent.quantity,
            average_fill_price=Decimal("1.08000"),
        )


def test_processed_event_ids_are_bounded(stack: Stack) -> None:
    stack.applier = type(stack.applier)(stack.store, stack.clock, max_processed_event_ids=4)
    intent = make_intent()
    stack.applier.record_order_intent(intent, venue="mt4")
    stack.applier.record_submitted(intent.order_intent_id)
    stack.applier.record_acknowledged(intent.order_intent_id, venue_order_id="ord-1")
    for index in range(6):
        stack.applier.record_partial_fill(
            intent.order_intent_id,
            event_id=f"fill-{index}",
            sequence=index,
            filled_quantity=Decimal("0.01"),
            average_fill_price=Decimal("1.08000"),
        )
    record = get_order(stack.store, intent.order_intent_id)
    assert len(record.processed_event_ids) == 4
    assert record.filled_quantity == Decimal("0.06")


def test_restart_preserves_state_without_replay(stack: Stack) -> None:
    """A fresh engine over the same store sees exactly the persisted state."""
    intent = make_intent()
    stack.applier.record_order_intent(intent, venue="mt4")
    stack.applier.record_submitted(intent.order_intent_id)
    stack.applier.record_acknowledged(intent.order_intent_id, venue_order_id="ord-1")

    restarted = Stack(store=stack.store, clock=stack.clock)
    record = get_order(restarted.store, intent.order_intent_id)
    assert record.state is OrderState.ACKNOWLEDGED
    assert record.version == 3

    restarted.applier.record_fill(
        intent.order_intent_id,
        event_id="fill-1",
        sequence=1,
        filled_quantity=intent.quantity,
        average_fill_price=Decimal("1.08000"),
    )
    assert get_order(restarted.store, intent.order_intent_id).state is OrderState.FILLED


def test_timestamps_advance_with_clock(stack: Stack) -> None:
    intent = make_intent()
    stack.applier.record_order_intent(intent, venue="mt4")
    stack.clock.advance(timedelta(seconds=1))
    submitted = stack.applier.record_submitted(intent.order_intent_id)
    assert submitted.submitted_at == stack.clock.now()
    assert submitted.submitted_at is not None
    assert submitted.created_at < submitted.submitted_at
