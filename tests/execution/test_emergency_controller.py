"""EmergencyController DoD tests: levels, gating, side effects, dead man switch.

Definition of Done (INV-7, architecture §10):

- the four levels gate exactly the right actions;
- EMERGENCY_KILL cancels pending orders and flattens **only** when the policy
  explicitly enables it;
- heartbeat loss enters the safe execution state with a CRITICAL alert, blocks
  new entries and never touches broker SL/TP or auto-closes positions;
- every action is audited; the controller works with no LLM or strategy
  process anywhere in the import graph.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from core.domain.enums import DeadManSwitchReason, EmergencyLevel
from engines.execution.emergency import (
    EMERGENCY_STRATEGY_ID,
    EmergencyController,
    EmergencyControlViolation,
    EmergencyPolicy,
)

from execution_helpers import Stack, make_intent


class RecordingCanceller:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, *, reason: str) -> list[str]:
        self.calls.append(reason)
        return ["order-1", "order-2"]


class RecordingFlattener:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, *, reason: str) -> list[str]:
        self.calls.append(reason)
        return ["pos-1"]


def build(
    stack: Stack,
    *,
    policy: EmergencyPolicy | None = None,
) -> tuple[EmergencyController, RecordingCanceller, RecordingFlattener]:
    canceller = RecordingCanceller()
    flattener = RecordingFlattener()
    controller = EmergencyController(
        stack.emergency_store,
        stack.clock,
        policy=policy or EmergencyPolicy(),
        audit=stack.audit,
        events=stack.events,
        alerts=stack.alerts,
        pending_canceller=canceller,
        flattener=flattener,
    )
    return controller, canceller, flattener


# ── Levels: gating semantics ─────────────────────────────────────────────
def test_strategy_kill_blocks_only_that_strategy() -> None:
    stack = Stack()
    controller, _, _ = build(stack)
    controller.activate(
        EmergencyLevel.STRATEGY_KILL, target="strategy-A", actor="ops", reason="test"
    )
    with pytest.raises(EmergencyControlViolation):
        controller.assert_can_enter("strategy-A", "EURUSD")
    with pytest.raises(EmergencyControlViolation):
        controller.assert_can_enter("strategy-A", "XAUUSD")
    controller.assert_can_enter("strategy-B", "EURUSD")  # no raise
    controller.assert_can_enter("strategy-B", "XAUUSD")  # no raise
    assert controller.strategy_killed("strategy-A") is True
    assert controller.strategy_killed("strategy-B") is False


def test_instrument_kill_blocks_only_that_instrument() -> None:
    stack = Stack()
    controller, _, _ = build(stack)
    controller.activate(EmergencyLevel.INSTRUMENT_KILL, target="XAUUSD", actor="ops", reason="test")
    with pytest.raises(EmergencyControlViolation):
        controller.assert_can_enter("strategy-A", "XAUUSD")
    controller.assert_can_enter("strategy-A", "EURUSD")  # no raise
    assert controller.instrument_killed("XAUUSD") is True


def test_no_new_positions_blocks_everything_platform_wide() -> None:
    stack = Stack()
    controller, _, _ = build(stack)
    controller.activate(EmergencyLevel.NO_NEW_POSITIONS, actor="ops", reason="risk event")
    assert controller.new_entries_blocked() is True
    for strategy_id in ("strategy-A", "strategy-B"):
        for instrument_id in ("EURUSD", "XAUUSD"):
            with pytest.raises(EmergencyControlViolation):
                controller.assert_can_enter(strategy_id, instrument_id)


def test_emergency_kill_blocks_entries_and_reports() -> None:
    stack = Stack()
    controller, _, _ = build(stack)
    controller.activate(EmergencyLevel.EMERGENCY_KILL, actor="ops", reason="flash crash")
    assert controller.emergency_kill_active() is True
    assert controller.new_entries_blocked() is True
    with pytest.raises(EmergencyControlViolation) as exc:
        controller.assert_can_enter("strategy-A", "EURUSD")
    assert EmergencyLevel.EMERGENCY_KILL.value in exc.value.reason_codes


def test_deactivate_restores_entries() -> None:
    stack = Stack()
    controller, _, _ = build(stack)
    controller.activate(EmergencyLevel.NO_NEW_POSITIONS, actor="ops", reason="test")
    controller.deactivate(EmergencyLevel.NO_NEW_POSITIONS, actor="ops", reason="resolved")
    controller.assert_can_enter("strategy-A", "EURUSD")  # no raise
    assert controller.new_entries_blocked() is False
    # history row remains inactive
    stored = stack.emergency_store.get_control(EmergencyLevel.NO_NEW_POSITIONS)
    assert stored is not None and stored.active is False


def test_targeted_levels_require_a_target() -> None:
    stack = Stack()
    controller, _, _ = build(stack)
    with pytest.raises(ValueError):
        controller.activate(EmergencyLevel.STRATEGY_KILL, actor="ops", reason="test")
    with pytest.raises(ValueError):
        controller.activate(EmergencyLevel.INSTRUMENT_KILL, actor="ops", reason="test")
    with pytest.raises(ValueError):
        controller.activate(
            EmergencyLevel.NO_NEW_POSITIONS, target="EURUSD", actor="ops", reason="x"
        )


# ── EMERGENCY_KILL side effects ──────────────────────────────────────────
def test_emergency_kill_cancels_pending_orders() -> None:
    stack = Stack()
    controller, canceller, flattener = build(stack)
    controller.activate(EmergencyLevel.EMERGENCY_KILL, actor="ops", reason="test")
    assert len(canceller.calls) == 1
    assert flattener.calls == []  # flatten is opt-in only


def test_emergency_kill_flattens_only_when_configured() -> None:
    stack = Stack()
    policy = EmergencyPolicy(flatten_on_emergency_kill=True)
    controller, canceller, flattener = build(stack, policy=policy)
    controller.activate(EmergencyLevel.EMERGENCY_KILL, actor="ops", reason="test")
    assert len(canceller.calls) == 1
    assert len(flattener.calls) == 1
    assert any(e.action == "emergency.cancel_pending" for e in stack.audit_sink.entries)
    assert any(e.action == "emergency.flatten" for e in stack.audit_sink.entries)


def test_activation_and_deactivation_are_audited() -> None:
    stack = Stack()
    controller, _, _ = build(stack)
    controller.activate(EmergencyLevel.EMERGENCY_KILL, actor="ops", reason="test")
    controller.deactivate(EmergencyLevel.EMERGENCY_KILL, actor="ops", reason="resolved")
    actions = {e.action for e in stack.audit_sink.entries}
    assert "emergency.activated" in actions
    assert "emergency.deactivated" in actions
    names = {e.event_name for e in stack.events.events}
    assert "system.emergency.activated" in names
    assert "system.emergency.deactivated" in names
    assert any(
        a.kind == "EMERGENCY_KILL_ACTIVATED" and a.severity == "CRITICAL"
        for a in stack.alerts.alerts
    )


def test_controls_persist_across_controller_instances() -> None:
    stack = Stack()
    controller, _, _ = build(stack)
    controller.activate(
        EmergencyLevel.STRATEGY_KILL, target="strategy-A", actor="ops", reason="test"
    )
    restarted = EmergencyController(stack.emergency_store, stack.clock, policy=EmergencyPolicy())
    assert restarted.strategy_killed("strategy-A") is True
    with pytest.raises(EmergencyControlViolation):
        restarted.assert_can_enter("strategy-A", "EURUSD")


# ── Dead man switch ──────────────────────────────────────────────────────
def test_heartbeat_loss_engages_safe_execution_state() -> None:
    stack = Stack()
    policy = EmergencyPolicy(heartbeat_timeout=timedelta(seconds=6))
    controller, canceller, flattener = build(stack, policy=policy)
    stack.clock.advance(timedelta(seconds=7))
    state = controller.check_dead_man()
    assert state.safe_execution_state is True
    assert DeadManSwitchReason.HEARTBEAT_LOST.value in state.reason_codes
    assert controller.safe_execution_state_active() is True
    assert controller.new_entries_blocked() is True
    with pytest.raises(EmergencyControlViolation):
        controller.assert_can_enter("strategy-A", "EURUSD")
    # No broker action at all: SL/TP untouched, no cancels, no flatten.
    assert canceller.calls == []
    assert flattener.calls == []
    assert any(
        a.kind == "DEAD_MAN_SWITCH_ENGAGED" and a.severity == "CRITICAL"
        for a in stack.alerts.alerts
    )
    assert any(e.action == "dead_man.engaged" for e in stack.audit_sink.entries)
    assert "system.emergency.heartbeat_lost" in {e.event_name for e in stack.events.events}


def test_heartbeat_loss_is_idempotent_single_alert() -> None:
    stack = Stack()
    policy = EmergencyPolicy(heartbeat_timeout=timedelta(seconds=6))
    controller, _, _ = build(stack, policy=policy)
    stack.clock.advance(timedelta(seconds=7))
    controller.check_dead_man()
    stack.clock.advance(timedelta(seconds=10))
    controller.check_dead_man()
    assert len([a for a in stack.alerts.alerts if a.kind == "DEAD_MAN_SWITCH_ENGAGED"]) == 1


def test_heartbeat_keeps_switch_quiet_and_restore_clears_state() -> None:
    stack = Stack()
    policy = EmergencyPolicy(heartbeat_timeout=timedelta(seconds=6))
    controller, _, _ = build(stack, policy=policy)
    for _ in range(3):
        stack.clock.advance(timedelta(seconds=2))
        controller.on_heartbeat(stack.clock.now())
    assert controller.safe_execution_state_active() is False

    # Loss → engaged; heartbeat → restored with INFO alert and audit.
    stack.clock.advance(timedelta(seconds=7))
    controller.check_dead_man()
    assert controller.safe_execution_state_active() is True
    controller.on_heartbeat(stack.clock.now())
    assert controller.safe_execution_state_active() is False
    assert controller.new_entries_blocked() is False
    controller.assert_can_enter("strategy-A", "EURUSD")  # no raise
    assert any(a.kind == "DEAD_MAN_SWITCH_RESTORED" for a in stack.alerts.alerts)
    assert any(e.action == "dead_man.restored" for e in stack.audit_sink.entries)
    assert "system.emergency.heartbeat_restored" in {e.event_name for e in stack.events.events}


def test_heartbeat_loss_flattens_only_with_explicit_policy() -> None:
    stack = Stack()
    policy = EmergencyPolicy(heartbeat_timeout=timedelta(seconds=6), flatten_on_heartbeat_loss=True)
    controller, canceller, flattener = build(stack, policy=policy)
    stack.clock.advance(timedelta(seconds=7))
    controller.check_dead_man()
    assert flattener.calls == ["dead man switch: heartbeat lost"]
    assert canceller.calls == []  # connectivity loss does NOT cancel pending orders


def test_disabled_dead_man_switch_never_engages() -> None:
    stack = Stack()
    policy = EmergencyPolicy(dead_man_switch_enabled=False, heartbeat_timeout=timedelta(seconds=6))
    controller, _, _ = build(stack, policy=policy)
    stack.clock.advance(timedelta(hours=1))
    state = controller.check_dead_man()
    assert state.safe_execution_state is False
    controller.assert_can_enter("strategy-A", "EURUSD")  # no raise


def test_dead_man_state_survives_controller_restart() -> None:
    stack = Stack()
    policy = EmergencyPolicy(heartbeat_timeout=timedelta(seconds=6))
    controller, _, _ = build(stack, policy=policy)
    stack.clock.advance(timedelta(seconds=7))
    controller.check_dead_man()
    restarted = EmergencyController(stack.emergency_store, stack.clock, policy=policy)
    assert restarted.safe_execution_state_active() is True
    with pytest.raises(EmergencyControlViolation):
        restarted.assert_can_enter("strategy-A", "EURUSD")


# ── Emergency close authorization ────────────────────────────────────────
def test_emergency_close_authorization_requires_kill_and_policy() -> None:
    stack = Stack()
    policy = EmergencyPolicy(flatten_on_emergency_kill=True)
    controller, _, _ = build(stack, policy=policy)
    intent = make_intent(strategy_id=EMERGENCY_STRATEGY_ID)
    with pytest.raises(EmergencyControlViolation):  # no kill active yet
        controller.assert_emergency_close_authorized(intent)
    controller.activate(EmergencyLevel.EMERGENCY_KILL, actor="ops", reason="test")
    controller.assert_emergency_close_authorized(intent)  # no raise

    non_emergency = make_intent(strategy_id="strategy-A")
    with pytest.raises(EmergencyControlViolation):
        controller.assert_emergency_close_authorized(non_emergency)
