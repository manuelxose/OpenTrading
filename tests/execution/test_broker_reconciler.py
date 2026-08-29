"""BrokerReconciler DoD tests: the five comparison axes and the
explainable-vs-material resolution matrix (ADR-0021)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from core.domain.enums import DiscrepancyCode, OrderState, PositionSide
from core.schemas.execution import ExecutionPosition
from core.schemas.trading import OrderIntent

from execution_helpers import (
    Stack,
    get_order,
    make_broker_view,
    make_intent,
    make_venue_view_position,
)


@pytest.fixture()
def stack() -> Stack:
    return Stack()


def _live_order(stack: Stack, state: OrderState) -> OrderIntent:
    intent = make_intent()
    stack.applier.record_order_intent(intent, venue="mt4")
    stack.applier.record_submitted(intent.order_intent_id)
    if state is OrderState.ACKNOWLEDGED:
        stack.applier.record_acknowledged(intent.order_intent_id, venue_order_id="ord-1")
    return intent


def test_clean_run_with_nothing_persisted(stack: Stack) -> None:
    run = stack.reconciler.reconcile(make_broker_view())
    assert run.material_discrepancies == 0
    assert run.discrepancies == ()
    assert run.orders_reconciled == 0


def test_in_flight_order_is_consistent(stack: Stack) -> None:
    intent = _live_order(stack, OrderState.ACKNOWLEDGED)
    run = stack.reconciler.reconcile(
        make_broker_view(open_order_intent_ids=(intent.order_intent_id,))
    )
    assert run.material_discrepancies == 0
    assert run.discrepancies == ()


def test_ack_lost_is_healed(stack: Stack) -> None:
    intent = _live_order(stack, OrderState.SUBMITTED)
    run = stack.reconciler.reconcile(
        make_broker_view(open_order_intent_ids=(intent.order_intent_id,))
    )
    assert run.material_discrepancies == 0
    assert run.orders_resolved == 1
    assert any(d.code is DiscrepancyCode.ORDER_ACK_LOST for d in run.discrepancies)
    assert get_order(stack.store, intent.order_intent_id).state is OrderState.ACKNOWLEDGED


def test_never_acknowledged_order_is_closed_as_explainable(stack: Stack) -> None:
    intent = _live_order(stack, OrderState.SUBMITTED)
    run = stack.reconciler.reconcile(make_broker_view())  # venue knows nothing
    assert run.material_discrepancies == 0
    assert run.orders_resolved == 1
    assert any(d.code is DiscrepancyCode.ORDER_NEVER_ACKNOWLEDGED for d in run.discrepancies)
    assert get_order(stack.store, intent.order_intent_id).state is OrderState.RECONCILED


def test_fill_event_lost_is_healed_from_broker_position(stack: Stack) -> None:
    intent = _live_order(stack, OrderState.ACKNOWLEDGED)
    run = stack.reconciler.reconcile(
        make_broker_view(
            positions=(
                make_venue_view_position(
                    order_intent_id=intent.order_intent_id, quantity=intent.quantity
                ),
            )
        )
    )
    assert run.material_discrepancies == 0
    assert any(d.code is DiscrepancyCode.FILL_EVENT_LOST for d in run.discrepancies)
    record = get_order(stack.store, intent.order_intent_id)
    assert record.state is OrderState.FILLED
    assert record.venue_position_id == "pos-1"
    positions = stack.store.list_positions(open_only=True)
    assert len(positions) == 1
    assert positions[0].order_intent_id == intent.order_intent_id


def test_missing_acknowledged_order_is_material(stack: Stack) -> None:
    intent = _live_order(stack, OrderState.ACKNOWLEDGED)
    run = stack.reconciler.reconcile(make_broker_view())
    assert run.material_discrepancies == 1
    assert any(d.code is DiscrepancyCode.MISSING_BROKER_ORDER for d in run.discrepancies)
    assert get_order(stack.store, intent.order_intent_id).state is OrderState.ACKNOWLEDGED


def test_unexpected_broker_order_is_material(stack: Stack) -> None:
    stranger = uuid4()
    run = stack.reconciler.reconcile(make_broker_view(open_order_intent_ids=(stranger,)))
    assert run.material_discrepancies == 1
    assert any(d.code is DiscrepancyCode.UNEXPECTED_BROKER_ORDER for d in run.discrepancies)


def test_unexpected_manual_broker_position_is_material(stack: Stack) -> None:
    run = stack.reconciler.reconcile(
        make_broker_view(positions=(make_venue_view_position(order_intent_id=None),))
    )
    assert run.material_discrepancies == 1
    assert any(d.code is DiscrepancyCode.UNEXPECTED_BROKER_POSITION for d in run.discrepancies)


def test_quantity_mismatch_on_known_position_is_material(stack: Stack) -> None:
    intent = _live_order(stack, OrderState.ACKNOWLEDGED)
    stack.applier.record_fill(
        intent.order_intent_id,
        event_id="fill-1",
        sequence=1,
        filled_quantity=intent.quantity,
        average_fill_price=Decimal("1.08000"),
        venue_position_id="pos-1",
    )
    stack.store.upsert_position(
        ExecutionPosition(
            venue_position_id="pos-1",
            account_id="acct-1",
            instrument_id="EURUSD",
            side=PositionSide.LONG,
            quantity=intent.quantity,
            average_entry_price=Decimal("1.08000"),
            order_intent_id=intent.order_intent_id,
            opened_at=stack.clock.now(),
            updated_at=stack.clock.now(),
        )
    )
    run = stack.reconciler.reconcile(
        make_broker_view(
            positions=(
                make_venue_view_position(
                    venue_position_id="pos-1",
                    quantity=Decimal("0.20"),  # broker says double
                ),
            )
        )
    )
    assert run.material_discrepancies == 1
    assert any(d.code is DiscrepancyCode.QUANTITY_MISMATCH for d in run.discrepancies)


def test_identifier_mismatch_on_known_position_is_material(stack: Stack) -> None:
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
    run = stack.reconciler.reconcile(
        make_broker_view(
            positions=(
                make_venue_view_position(venue_position_id="pos-1", side=PositionSide.SHORT),
            )
        )
    )
    assert run.material_discrepancies == 1
    assert any(d.code is DiscrepancyCode.IDENTIFIER_MISMATCH for d in run.discrepancies)


def test_price_drift_is_a_warning_and_broker_price_wins(stack: Stack) -> None:
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
    run = stack.reconciler.reconcile(
        make_broker_view(
            positions=(
                make_venue_view_position(
                    venue_position_id="pos-1", average_entry_price=Decimal("1.12000")
                ),
            )
        )
    )
    assert run.material_discrepancies == 0
    assert any(
        d.code is DiscrepancyCode.PRICE_DRIFT and d.severity == "WARNING" for d in run.discrepancies
    )
    stored = stack.store.get_position("pos-1")
    assert stored is not None
    assert stored.average_entry_price == Decimal("1.12000")


def test_position_closed_at_venue_is_explainable(stack: Stack) -> None:
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
    run = stack.reconciler.reconcile(make_broker_view())
    assert run.material_discrepancies == 0
    assert any(d.code is DiscrepancyCode.POSITION_CLOSED_AT_VENUE for d in run.discrepancies)
    stored = stack.store.get_position("pos-1")
    assert stored is not None
    assert stored.closed_at is not None


def test_unmatched_position_adopted_via_unique_live_order(stack: Stack) -> None:
    intent = _live_order(stack, OrderState.ACKNOWLEDGED)
    run = stack.reconciler.reconcile(
        make_broker_view(
            positions=(
                make_venue_view_position(
                    order_intent_id=None,  # no provenance link — only qty/instrument match
                    quantity=intent.quantity,
                ),
            )
        )
    )
    assert run.material_discrepancies == 0
    assert any(d.code is DiscrepancyCode.FILL_EVENT_LOST for d in run.discrepancies)
    record = get_order(stack.store, intent.order_intent_id)
    assert record.state is OrderState.FILLED
    assert record.venue_position_id == "pos-1"


def test_unmatched_position_with_ambiguous_candidates_is_material(stack: Stack) -> None:
    first = _live_order(stack, OrderState.ACKNOWLEDGED)
    second = _live_order(stack, OrderState.ACKNOWLEDGED)
    assert first.order_intent_id != second.order_intent_id
    run = stack.reconciler.reconcile(
        make_broker_view(
            positions=(make_venue_view_position(order_intent_id=None, quantity=Decimal("0.10")),)
        )
    )
    # Two silent acknowledged orders are already material; the ambiguous
    # position is material on top of that.
    assert any(d.code is DiscrepancyCode.UNEXPECTED_BROKER_POSITION for d in run.discrepancies)
    assert run.material_discrepancies >= 3


def test_filled_order_still_open_at_venue_is_material(stack: Stack) -> None:
    intent = _live_order(stack, OrderState.ACKNOWLEDGED)
    stack.applier.record_fill(
        intent.order_intent_id,
        event_id="fill-1",
        sequence=1,
        filled_quantity=intent.quantity,
        average_fill_price=Decimal("1.08000"),
    )
    run = stack.reconciler.reconcile(
        make_broker_view(open_order_intent_ids=(intent.order_intent_id,))
    )
    assert run.material_discrepancies == 1
    assert any(d.code is DiscrepancyCode.IDENTIFIER_MISMATCH for d in run.discrepancies)


def test_disconnected_broker_reports_material_without_mutations(stack: Stack) -> None:
    intent = _live_order(stack, OrderState.SUBMITTED)
    run = stack.reconciler.reconcile(
        make_broker_view(broker_connected=False, open_order_intent_ids=(intent.order_intent_id,))
    )
    assert run.material_discrepancies == 1
    assert any(d.code is DiscrepancyCode.BROKER_UNREACHABLE for d in run.discrepancies)
    assert get_order(stack.store, intent.order_intent_id).state is OrderState.SUBMITTED


def test_terminal_orders_become_reconciled(stack: Stack) -> None:
    intent = _live_order(stack, OrderState.ACKNOWLEDGED)
    stack.applier.record_fill(
        intent.order_intent_id,
        event_id="fill-1",
        sequence=1,
        filled_quantity=intent.quantity,
        average_fill_price=Decimal("1.08000"),
    )
    run = stack.reconciler.reconcile(make_broker_view())
    assert run.material_discrepancies == 0
    assert run.orders_reconciled == 1
    assert get_order(stack.store, intent.order_intent_id).state is OrderState.RECONCILED


def test_run_persists_last_sequences(stack: Stack) -> None:
    run = stack.reconciler.reconcile(make_broker_view(last_sequences={"strategy-A": 7, "CORE": 3}))
    assert run.last_sequences == {"strategy-A": 7, "CORE": 3}


def test_reconcile_advances_clock_stamp(stack: Stack) -> None:
    stack.clock.advance(timedelta(seconds=5))
    run = stack.reconciler.reconcile(make_broker_view())
    assert run.compared_at >= run.started_at
