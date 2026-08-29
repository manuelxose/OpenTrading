"""SafeModeController DoD tests: gate semantics, alerts, audit, idempotency."""

from __future__ import annotations

from datetime import timedelta

import pytest
from core.domain.enums import SafeModeAction
from engines.execution.safe_mode import SafeModeViolation

from execution_helpers import Stack


@pytest.fixture()
def stack() -> Stack:
    return Stack()


def test_inactive_mode_allows_everything(stack: Stack) -> None:
    assert stack.controller.active is False
    for action in SafeModeAction:
        stack.controller.assert_allowed(action)  # no raise


def test_enter_blocks_new_entries_only(stack: Stack) -> None:
    stack.controller.enter(["RECONCILIATION_DIVERGENCE"], note="divergence")
    with pytest.raises(SafeModeViolation):
        stack.controller.assert_allowed(SafeModeAction.NEW_ENTRY)

    for action in (
        SafeModeAction.RISK_REDUCING,
        SafeModeAction.RECONCILIATION,
        SafeModeAction.MONITORING,
    ):
        stack.controller.assert_allowed(action)  # no raise

    assert stack.controller.can_submit_new_entries() is False


def test_enter_produces_event_audit_and_alert(stack: Stack) -> None:
    stack.controller.enter(["BROKER_UNREACHABLE"], note="partition")
    event_names = [e.event_name for e in stack.events.events]
    assert "system.safe_mode.entered" in event_names
    assert any(e.action == "safe_mode.entered" for e in stack.audit_sink.entries)
    assert len(stack.alerts.alerts) == 1
    alert = stack.alerts.alerts[0]
    assert alert.kind == "SAFE_MODE_ENTERED"
    assert alert.severity == "CRITICAL"


def test_enter_is_idempotent(stack: Stack) -> None:
    first = stack.controller.enter(["RECONCILIATION_DIVERGENCE"])
    stack.clock.advance(timedelta(seconds=10))
    second = stack.controller.enter(["BROKER_UNREACHABLE"])
    assert second.active is True
    assert second.since == first.since  # original entry time preserved
    assert set(second.reason_codes) == {"RECONCILIATION_DIVERGENCE", "BROKER_UNREACHABLE"}
    assert len(stack.alerts.alerts) == 1  # no duplicate alert


def test_exit_restores_new_entries(stack: Stack) -> None:
    stack.controller.enter(["RECONCILIATION_DIVERGENCE"])
    exited = stack.controller.exit(note="clean reconciliation")
    assert exited.active is False
    assert exited.exited_at is not None
    stack.controller.assert_allowed(SafeModeAction.NEW_ENTRY)  # no raise
    assert stack.controller.can_submit_new_entries() is True
    assert any(e.event_name == "system.safe_mode.exited" for e in stack.events.events)
    assert stack.alerts.alerts[-1].kind == "SAFE_MODE_EXITED"


def test_exit_when_inactive_is_a_noop(stack: Stack) -> None:
    before = len(stack.alerts.alerts)
    stack.controller.exit(note="nothing to exit")
    assert len(stack.alerts.alerts) == before


def test_state_persists_across_controller_instances(stack: Stack) -> None:
    stack.controller.enter(["OVERFILL_DETECTED"], note="overfill")
    restarted = Stack(store=stack.store, clock=stack.clock)
    assert restarted.controller.active is True
    with pytest.raises(SafeModeViolation):
        restarted.controller.assert_allowed(SafeModeAction.NEW_ENTRY)
