"""Integration tests: execution-state persistence against real PostgreSQL.

Requires ``make up`` (PostgreSQL) and ``OT_INTEGRATION=1`` — otherwise skipped,
like the other integration suites. Verifies the Postgres store end-to-end:
order CAS, positions, reconciliation runs, and the SAFE_MODE singleton row.
"""

from __future__ import annotations

import os
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from core.config.settings import get_settings
from core.domain.enums import OrderSide, OrderState, OrderType, PositionSide
from core.schemas.execution import (
    ExecutionPosition,
    OrderRecord,
    ReconciliationRun,
    SafeModeRecord,
)
from engines.execution.persistence import PostgresExecutionStateStore, StaleStateError

from execution_helpers import T0

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("OT_INTEGRATION"),
        reason="local stack not running (make up)",
    ),
]


@pytest.fixture()
def store() -> PostgresExecutionStateStore:
    return PostgresExecutionStateStore(get_settings().postgres_dsn)


def _order(order_intent_id: UUID) -> OrderRecord:
    return OrderRecord(
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


def test_postgres_order_roundtrip_and_cas(store: PostgresExecutionStateStore) -> None:
    order_intent_id = uuid4()
    store.save_order(_order(order_intent_id))
    loaded = store.get_order(order_intent_id)
    assert loaded is not None
    assert loaded.state is OrderState.ORDER_INTENT

    bumped = loaded.model_copy(
        update={"state": OrderState.SUBMITTED, "submitted_at": T0, "version": 2}
    )
    stored = store.update_order(bumped, expected_version=1)
    assert stored.version == 2
    assert store.get_order(order_intent_id).state is OrderState.SUBMITTED

    with pytest.raises(StaleStateError):
        store.update_order(bumped, expected_version=1)


def test_postgres_positions_and_runs(store: PostgresExecutionStateStore) -> None:
    position = ExecutionPosition(
        venue_position_id=f"it-pos-{uuid4().hex[:8]}",
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
    assert store.get_position(position.venue_position_id) is not None
    assert position in store.list_positions(open_only=True)

    run = ReconciliationRun(
        run_id=uuid4(),
        started_at=T0,
        compared_at=T0,
        broker_reachable=True,
        last_sequences={"strategy-A": 1},
    )
    store.save_reconciliation_run(run)
    assert store.list_reconciliation_runs(limit=5)[-1].run_id == run.run_id


def test_postgres_safe_mode_singleton(store: PostgresExecutionStateStore) -> None:
    assert store.get_safe_mode().active is False
    record = SafeModeRecord(
        active=True,
        since=T0,
        reason_codes=("BROKER_UNREACHABLE",),
        note="integration",
        updated_at=T0,
    )
    store.set_safe_mode(record)
    assert store.get_safe_mode().active is True
    cleared = SafeModeRecord(active=False, updated_at=T0)
    store.set_safe_mode(cleared)
    assert store.get_safe_mode().active is False
