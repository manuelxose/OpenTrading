from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from engines.execution.live_gate import ApprovalStatus, KillScope
from engines.execution.live_gate_persistence import (
    PostgresApprovalStore,
    live_approvals_table,
)
from sqlalchemy import create_engine
from test_live_gate import _gate, _price

from execution_helpers import Stack, make_intent


def test_approval_and_kill_state_survive_store_restart() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    live_approvals_table.metadata.create_all(engine)
    store1 = PostgresApprovalStore("sqlite+pysqlite:///:memory:", engine=engine)
    stack = Stack()
    gate = _gate(stack)
    intent = make_intent(operating_mode="LIVE_GATED")
    record = gate.request_approval(intent, _price(stack))

    store1.put(record)
    store1.set_kill(KillScope.EMERGENCY, None, "operator", "incident", datetime.now(UTC))
    store2 = PostgresApprovalStore("sqlite+pysqlite:///:memory:", engine=engine)

    assert store2.get(intent.order_intent_id) == record
    assert not store2.put_if_absent(record)
    assert (KillScope.EMERGENCY, None) in store2.active_kills()
    consumed = replace(
        record,
        status=ApprovalStatus.CONSUMED,
        consumed_at=stack.clock.now(),
    )
    assert store2.compare_and_put(ApprovalStatus.WAITING_FOR_HUMAN, consumed)
    assert not store1.compare_and_put(ApprovalStatus.WAITING_FOR_HUMAN, consumed)


def test_unknown_approval_is_absent() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    live_approvals_table.metadata.create_all(engine)
    store = PostgresApprovalStore("sqlite+pysqlite:///:memory:", engine=engine)
    assert store.get(uuid4()) is None
