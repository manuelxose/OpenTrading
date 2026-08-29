"""Command gate tests: expiration, duplicates, sequence validation (ADR-0020)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from adapters.mt4.errors import Mt4ErrorCode
from adapters.mt4.guards import CommandGate
from adapters.mt4.protocol import OrderAck
from core.clock.clocks import VirtualClock
from core.domain.enums import OrderType
from tests.unit.mt4.helpers import T0, make_modify, make_submit


def _ack() -> OrderAck:
    return OrderAck(
        message_id=uuid4(),
        timestamp=T0,
        sequence=1,
        order_intent_id=uuid4(),
        status="ACKNOWLEDGED",
    )


def test_first_command_accepted() -> None:
    gate = CommandGate(VirtualClock(T0))
    outcome = gate.evaluate(make_submit())
    assert outcome.accepted
    assert outcome.error is None


def test_expired_command_rejected() -> None:
    gate = CommandGate(VirtualClock(T0))
    expired = make_submit(timestamp=T0 - timedelta(minutes=5), expires_in_seconds=60)
    outcome = gate.evaluate(expired)
    assert not outcome.accepted
    assert outcome.error is not None
    assert outcome.error.code is Mt4ErrorCode.COMMAND_EXPIRED


def test_command_at_exact_expiry_is_rejected() -> None:
    gate = CommandGate(VirtualClock(T0))
    expiring_now = make_submit(timestamp=T0 - timedelta(seconds=1), expires_in_seconds=1)
    outcome = gate.evaluate(expiring_now)
    assert not outcome.accepted
    assert outcome.error is not None
    assert outcome.error.code is Mt4ErrorCode.COMMAND_EXPIRED


def test_duplicate_intent_replays_original_reply() -> None:
    clock = VirtualClock(T0)
    gate = CommandGate(clock)
    command = make_submit()
    assert gate.evaluate(command).accepted
    gate.record(command, _ack())

    replay = gate.evaluate(command)
    assert not replay.accepted
    assert replay.replay is not None
    assert isinstance(replay.replay, OrderAck)
    assert replay.error is None


def test_same_intent_different_fields_is_conflict() -> None:
    gate = CommandGate(VirtualClock(T0))
    first = make_submit()
    gate.evaluate(first)
    gate.record(first, _ack())

    conflict = first.model_copy(update={"quantity": Decimal("0.99")})
    outcome = gate.evaluate(conflict)
    assert not outcome.accepted
    assert outcome.error is not None
    assert outcome.error.code is Mt4ErrorCode.INTENT_CONFLICT


def test_same_intent_100_times_never_accepted_twice() -> None:
    """Phase 6 DoD core guarantee at the gate level."""
    gate = CommandGate(VirtualClock(T0))
    command = make_submit()
    assert gate.evaluate(command).accepted
    gate.record(command, _ack())
    replayed = sum(1 for _ in range(99) if gate.evaluate(command).replay is not None)
    assert replayed == 99  # every re-delivery replays, none re-executes


def test_sequence_must_be_strictly_monotonic() -> None:
    gate = CommandGate(VirtualClock(T0))
    first = make_submit(sequence=1)
    second = make_submit(sequence=2)
    assert gate.evaluate(first).accepted
    gate.record(first, _ack())
    assert gate.evaluate(second).accepted
    gate.record(second, _ack())

    out_of_order = gate.evaluate(make_submit(sequence=2))
    assert not out_of_order.accepted
    assert out_of_order.error is not None
    assert out_of_order.error.code is Mt4ErrorCode.SEQUENCE_VIOLATION
    assert out_of_order.expected_sequence == 3


def test_sequence_gap_rejected() -> None:
    gate = CommandGate(VirtualClock(T0))
    first = make_submit(sequence=1)
    assert gate.evaluate(first).accepted
    gate.record(first, _ack())
    gap = gate.evaluate(make_submit(sequence=5))
    assert not gap.accepted
    assert gap.error is not None
    assert gap.error.code is Mt4ErrorCode.SEQUENCE_VIOLATION
    assert gap.expected_sequence == 2


def test_sequences_are_namespaced_by_strategy() -> None:
    gate = CommandGate(VirtualClock(T0))
    for strategy_id, sequence in (("A", 1), ("B", 1), ("A", 2)):
        command = make_submit(sequence=sequence, strategy_id=strategy_id)
        assert gate.evaluate(command).accepted, f"{strategy_id}/{sequence}"
        gate.record(command, _ack())


def test_duplicate_check_runs_before_sequence_check() -> None:
    """A retried intent is a replay even if its sequence is now stale."""
    clock = VirtualClock(T0)
    gate = CommandGate(clock)
    first = make_submit(sequence=1)
    gate.record(first, _ack())
    gate.record(make_submit(sequence=2), _ack())  # namespace moved on

    retry = first.model_copy(update={"message_id": uuid4(), "timestamp": T0})
    outcome = gate.evaluate(retry)
    assert outcome.replay is not None  # replay, not SEQUENCE_VIOLATION


def test_modify_may_amend_with_new_fields() -> None:
    """One intent can receive several different modifications; identical
    re-delivered modifications replay the stored outcome."""
    clock = VirtualClock(T0)
    gate = CommandGate(clock)
    intent = uuid4()
    submit = make_submit(
        sequence=1, order_intent_id=intent, order_type=OrderType.LIMIT, price=Decimal("1.05000")
    )
    gate.evaluate(submit)
    gate.record(submit, _ack())

    amend_one = make_modify(sequence=2, order_intent_id=intent, new_stop_loss=Decimal("1.04900"))
    assert gate.evaluate(amend_one).accepted
    gate.record(amend_one, _ack())

    # Same amendment re-delivered → replay; a new amendment → accepted.
    assert gate.evaluate(amend_one).replay is not None
    amend_two = make_modify(sequence=3, order_intent_id=intent, new_stop_loss=Decimal("1.04800"))
    assert gate.evaluate(amend_two).accepted
