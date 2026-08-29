"""Execution state store semantics: authoritative persistence + CAS."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from core.domain.enums import OrderSide, OrderState, OrderType, PositionSide
from core.schemas.execution import (
    ExecutionPosition,
    OrderRecord,
    ReconciliationDiscrepancy,
    ReconciliationRun,
    SafeModeRecord,
)
from engines.execution.persistence import InMemoryExecutionStateStore, StaleStateError

from execution_helpers import T0, new_clock


def _save_order_intent(store: InMemoryExecutionStateStore, order_intent_id: UUID) -> OrderRecord:
    return store.save_order(
        OrderRecord(
            order_intent_id=order_intent_id,
            state=OrderState.ORDER_INTENT,
            strategy_id="strategy-A",
            strategy_version="1.0.0",
            instrument_id="EURUSD",
            venue="mt4",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            requested_quantity=Decimal("0.10"),
            remaining_quantity=Decimal("0.10"),
            version=1,
            created_at=T0,
            updated_at=T0,
        )
    )


def test_order_roundtrip_and_versions() -> None:
    store = InMemoryExecutionStateStore()
    intent_id = uuid4()
    record = _save_order_intent(store, intent_id)
    loaded = store.get_order(intent_id)
    assert loaded is record
    assert loaded.version == 1
    assert loaded.state is OrderState.ORDER_INTENT


def test_update_order_compare_and_set() -> None:
    store = InMemoryExecutionStateStore()
    clock = new_clock()
    record = _save_order_intent(store, uuid4())
    clock.advance(timedelta(seconds=1))
    bumped = record.model_copy(
        update={"state": OrderState.SUBMITTED, "updated_at": clock.now(), "version": 2}
    )
    stored = store.update_order(bumped, expected_version=1)
    assert stored.version == 2
    assert store.get_order(record.order_intent_id) is bumped


def test_update_order_stale_version_raises() -> None:
    store = InMemoryExecutionStateStore()
    clock = new_clock()
    record = _save_order_intent(store, uuid4())
    bumped = record.model_copy(
        update={"state": OrderState.SUBMITTED, "updated_at": clock.now(), "version": 2}
    )
    with pytest.raises(StaleStateError):
        store.update_order(bumped, expected_version=7)


def test_update_order_wrong_next_version_raises() -> None:
    store = InMemoryExecutionStateStore()
    record = _save_order_intent(store, uuid4())
    bad = record.model_copy(update={"version": 5})
    with pytest.raises(ValueError, match="version"):
        store.update_order(bad, expected_version=1)


def test_save_order_twice_raises() -> None:
    store = InMemoryExecutionStateStore()
    intent_id = uuid4()
    _save_order_intent(store, intent_id)
    with pytest.raises(StaleStateError):
        _save_order_intent(store, intent_id)


def test_list_orders_preserves_creation_order() -> None:
    store = InMemoryExecutionStateStore()
    first = uuid4()
    second = uuid4()
    _save_order_intent(store, first)
    _save_order_intent(store, second)
    ids = [r.order_intent_id for r in store.list_orders()]
    assert ids == [first, second]


def test_position_roundtrip_and_open_filter() -> None:
    store = InMemoryExecutionStateStore()
    position = ExecutionPosition(
        venue_position_id="pos-1",
        account_id="acct-1",
        instrument_id="EURUSD",
        side=PositionSide.LONG,
        quantity=Decimal("0.10"),
        average_entry_price=Decimal("1.08"),
        order_intent_id=uuid4(),
        opened_at=T0,
        updated_at=T0,
    )
    store.upsert_position(position)
    assert store.get_position("pos-1") is position
    assert store.list_positions(open_only=True) == (position,)
    closed = position.model_copy(
        update={"closed_at": T0 + timedelta(seconds=1), "updated_at": T0 + timedelta(seconds=1)}
    )
    store.upsert_position(closed)
    assert store.list_positions(open_only=True) == ()
    assert store.list_positions(open_only=False) == (closed,)


def test_reconciliation_run_roundtrip() -> None:
    store = InMemoryExecutionStateStore()
    run = ReconciliationRun(
        run_id=uuid4(),
        started_at=T0,
        compared_at=T0,
        broker_reachable=True,
        discrepancies=(
            ReconciliationDiscrepancy(
                code="ORDER_ACK_LOST",
                severity="EXPLAINABLE",
                explanation="ack lost",
                resolution="ACKNOWLEDGED",
            ),
        ),
    )
    store.save_reconciliation_run(run)
    assert store.list_reconciliation_runs() == (run,)


def test_safe_mode_default_and_roundtrip() -> None:
    store = InMemoryExecutionStateStore()
    assert store.get_safe_mode().active is False
    record = SafeModeRecord(
        active=True,
        since=T0,
        reason_codes=("BROKER_UNREACHABLE",),
        note="partition",
        updated_at=T0,
    )
    store.set_safe_mode(record)
    assert store.get_safe_mode() is record


def test_get_order_missing_returns_none() -> None:
    store = InMemoryExecutionStateStore()
    assert store.get_order(uuid4()) is None
