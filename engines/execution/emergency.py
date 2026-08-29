"""Emergency control system: kill switches + dead man switch (INV-7, §10).

This module is deliberately **independent of every LLM and strategy process**:
it imports nothing from TradingAgents, strategy engines, research pipelines or
any LLM boundary. It is pure deterministic code over the clock and persisted
state, so emergency controls keep working even when every strategy process and
LLM is down, misbehaving or compromised (Definition of Done, INV-7).

The four levels (architecture §10):

``STRATEGY_KILL``
    disable one strategy — new entries for that ``strategy_id`` are rejected.
``INSTRUMENT_KILL``
    disable one instrument — new entries for that symbol are rejected.
``NO_NEW_POSITIONS``
    portfolio kill — new entries are rejected platform-wide.
``EMERGENCY_KILL``
    ``CANCEL_PENDING`` + ``NO_NEW_POSITIONS`` + flatten *only* when the policy
    explicitly enables it (``flatten_on_emergency_kill``).

Dead man switch:

- the Core feeds heartbeats via :meth:`EmergencyController.on_heartbeat`;
- :meth:`EmergencyController.check_dead_man` is evaluated on a deterministic
  cadence (submit path, event drains, reconciliation and the CLI monitor);
- heartbeat loss **never** touches broker-side SL/TP and **never** closes
  positions automatically — it only enters the safe execution state, blocks
  new entries and raises a CRITICAL alert, unless
  ``flatten_on_heartbeat_loss`` is explicitly configured.

Every activation, deactivation, side effect and dead-man transition is
persisted, audited, emitted as a canonical domain event and alerted on.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, Protocol
from uuid import uuid4

from core.audit.audit import AuditLogger
from core.clock.clocks import Clock
from core.domain.enums import (
    DeadManSwitchReason,
    EmergencyLevel,
    OrderSide,
    OrderType,
    PositionSide,
)
from core.schemas.execution import (
    DeadManSwitchState,
    EmergencyControlState,
    EmergencyEvent,
    ExecutionPosition,
    OperationalAlert,
    build_provenance,
)
from core.schemas.trading import OrderIntent

from engines.execution.emergency_persistence import EmergencyStore
from engines.execution.events import EventSink, make_event
from engines.execution.safe_mode import AlertSink

__all__ = [
    "EMERGENCY_STRATEGY_ID",
    "EmergencyControlViolation",
    "EmergencyController",
    "EmergencyPolicy",
    "PendingOrderCanceller",
    "PositionFlattener",
    "assert_emergency_closure_matches_positions",
]

#: Strategy identity stamped on emergency-generated closure intents. The live
#: authorizer recognizes it and routes it to the deterministic emergency
#: policy instead of the human approval gate (INV-1: deterministic code).
EMERGENCY_STRATEGY_ID = "CORE-EMERGENCY"


@dataclass(frozen=True, slots=True)
class EmergencyPolicy:
    """Configuration of the emergency control system (never changeable by LLMs)."""

    dead_man_switch_enabled: bool = True
    heartbeat_timeout: timedelta = timedelta(seconds=6)
    cancel_pending_on_emergency_kill: bool = True
    #: Explicit opt-in only: flattening is never implicit (§10).
    flatten_on_emergency_kill: bool = False
    flatten_on_heartbeat_loss: bool = False

    def __post_init__(self) -> None:
        if self.heartbeat_timeout <= timedelta(0):
            raise ValueError("heartbeat_timeout must be positive")


class PendingOrderCanceller(Protocol):
    """Callable that cancels every still-live order (``CANCEL_PENDING``)."""

    def __call__(self, *, reason: str) -> list[str]: ...


class PositionFlattener(Protocol):
    """Callable that closes every open position (``OPTIONALLY_FLATTEN``)."""

    def __call__(self, *, reason: str) -> list[str]: ...


class EmergencyControlViolation(RuntimeError):
    """Raised when an action is blocked by an active emergency control."""

    def __init__(self, reason_codes: Sequence[str]) -> None:
        codes = ", ".join(reason_codes) if reason_codes else "unspecified"
        super().__init__(f"action blocked by the emergency control system (reasons: {codes})")
        self.reason_codes = tuple(reason_codes)


_TARGETED_LEVELS = frozenset({EmergencyLevel.STRATEGY_KILL, EmergencyLevel.INSTRUMENT_KILL})


class EmergencyController:
    """Deterministic authority for kill switches and the dead man switch."""

    def __init__(
        self,
        store: EmergencyStore,
        clock: Clock,
        *,
        policy: EmergencyPolicy | None = None,
        audit: AuditLogger | None = None,
        events: EventSink | None = None,
        alerts: AlertSink | None = None,
        pending_canceller: PendingOrderCanceller | None = None,
        flattener: PositionFlattener | None = None,
        producer: str = "emergency-controller",
    ) -> None:
        self._store = store
        self._clock = clock
        self._policy = policy or EmergencyPolicy()
        self._audit = audit
        self._events = events
        self._alerts = alerts
        self._pending_canceller = pending_canceller
        self._flattener = flattener
        self._producer = producer
        # Heartbeat tracking is in-memory; only DMS transitions are persisted.
        self._armed_at = clock.now()
        self._last_heartbeat_at: datetime | None = None

    # ── Activation / deactivation ─────────────────────────────────────────
    def activate(
        self,
        level: EmergencyLevel,
        *,
        target: str | None = None,
        actor: str,
        reason: str,
    ) -> EmergencyControlState:
        """Activate one emergency level. EMERGENCY_KILL runs its side effects."""
        if not actor.strip():
            raise ValueError("an authenticated actor identity is required")
        self._validate_target(level, target)
        now = self._clock.now()
        state = EmergencyControlState(
            level=level,
            target=target,
            active=True,
            activated_by=actor.strip(),
            activated_at=now,
            reason=reason,
            updated_at=now,
        )
        stored = self._store.set_control(state)
        self._audit_record("emergency.activated", "OK", actor, target, level, reason)
        self._emit(
            "system.emergency.activated",
            level=level,
            target=target,
            active=True,
            actor=actor,
            reason=reason,
        )
        severity: Literal["CRITICAL", "WARNING"] = (
            "CRITICAL" if level is EmergencyLevel.EMERGENCY_KILL else "WARNING"
        )
        self._alert(
            f"{level.value}_ACTIVATED",
            severity,
            f"Emergency control activated: {level.value}",
            f"target={target or '<platform>'}; reason: {reason}",
        )
        if level is EmergencyLevel.EMERGENCY_KILL:
            self._run_emergency_side_effects(reason)
        return stored

    def deactivate(
        self,
        level: EmergencyLevel,
        *,
        target: str | None = None,
        actor: str,
        reason: str,
    ) -> EmergencyControlState:
        """Deactivate one emergency level (kept in history with ``active=False``)."""
        if not actor.strip():
            raise ValueError("an authenticated actor identity is required")
        self._validate_target(level, target)
        now = self._clock.now()
        was_active = self._kill_active(level, target)
        stored = self._store.clear_control(
            level, target, actor=actor.strip(), reason=reason, at=now
        )
        self._audit_record("emergency.deactivated", "OK", actor, target, level, reason)
        if not was_active:
            return stored
        self._emit(
            "system.emergency.deactivated",
            level=level,
            target=target,
            active=False,
            actor=actor,
            reason=reason,
        )
        if level is EmergencyLevel.EMERGENCY_KILL:
            self._alert(
                "EMERGENCY_KILL_DEACTIVATED",
                "INFO",
                "Emergency control deactivated: EMERGENCY_KILL",
                f"target={target or '<platform>'}; reason: {reason}",
            )
        return stored

    # ── Gating ────────────────────────────────────────────────────────────
    def blocked_reasons(self, strategy_id: str, instrument_id: str) -> tuple[str, ...]:
        """Reason codes explaining why a new entry is currently blocked (empty = allowed)."""
        reasons: list[str] = []
        for control in self._store.list_active_controls():
            if control.level is EmergencyLevel.STRATEGY_KILL and control.target == strategy_id:
                reasons.append(f"STRATEGY_KILL:{strategy_id}")
            elif (
                control.level is EmergencyLevel.INSTRUMENT_KILL and control.target == instrument_id
            ):
                reasons.append(f"INSTRUMENT_KILL:{instrument_id}")
            elif control.level is EmergencyLevel.NO_NEW_POSITIONS:
                reasons.append(EmergencyLevel.NO_NEW_POSITIONS.value)
            elif control.level is EmergencyLevel.EMERGENCY_KILL:
                reasons.append(EmergencyLevel.EMERGENCY_KILL.value)
        if self.safe_execution_state_active():
            reasons.append(DeadManSwitchReason.HEARTBEAT_LOST.value)
        return tuple(dict.fromkeys(reasons))

    def assert_can_enter(self, strategy_id: str, instrument_id: str) -> None:
        """Raise :class:`EmergencyControlViolation` if a new entry is blocked."""
        reasons = self.blocked_reasons(strategy_id, instrument_id)
        if reasons:
            raise EmergencyControlViolation(reasons)

    def new_entries_blocked(self) -> bool:
        """True when new entries are blocked platform-wide (INV-7)."""
        controls = self._store.list_active_controls()
        if any(
            c.level in (EmergencyLevel.NO_NEW_POSITIONS, EmergencyLevel.EMERGENCY_KILL)
            for c in controls
        ):
            return True
        return self.safe_execution_state_active()

    def strategy_killed(self, strategy_id: str) -> bool:
        return self._kill_active(EmergencyLevel.STRATEGY_KILL, strategy_id)

    def instrument_killed(self, instrument_id: str) -> bool:
        return self._kill_active(EmergencyLevel.INSTRUMENT_KILL, instrument_id)

    def emergency_kill_active(self) -> bool:
        return self._kill_active(EmergencyLevel.EMERGENCY_KILL, None)

    def active_controls(self) -> tuple[EmergencyControlState, ...]:
        return self._store.list_active_controls()

    def snapshot(self) -> dict[str, Any]:
        """Serializable summary for the operator API."""
        return {
            "active_controls": [c.model_dump(mode="json") for c in self.active_controls()],
            "dead_man_switch": self.dead_man_state().model_dump(mode="json"),
            "new_entries_blocked": self.new_entries_blocked(),
            "safe_execution_state": self.safe_execution_state_active(),
        }

    def _kill_active(self, level: EmergencyLevel, target: str | None) -> bool:
        return any(
            c.level is level and c.target == target for c in self._store.list_active_controls()
        )

    # ── Dead man switch ───────────────────────────────────────────────────
    def dead_man_state(self) -> DeadManSwitchState:
        return self._store.get_dead_man()

    def safe_execution_state_active(self) -> bool:
        return self._store.get_dead_man().safe_execution_state

    def on_heartbeat(self, received_at: datetime | None = None) -> None:
        """Feed one Core ↔ MT4 heartbeat; restores the safe state on recovery."""
        received = received_at or self._clock.now()
        self._last_heartbeat_at = received
        state = self._store.get_dead_man()
        engaged_reasons = (
            state.safe_execution_state
            and DeadManSwitchReason.HEARTBEAT_LOST.value in state.reason_codes
        )
        if engaged_reasons:
            restored = DeadManSwitchState(
                dead_man_switch_enabled=self._policy.dead_man_switch_enabled,
                heartbeat_timeout_seconds=self._policy.heartbeat_timeout.total_seconds(),
                armed_at=self._armed_at,
                last_heartbeat_at=received,
                safe_execution_state=False,
                heartbeat_lost_at=None,
                reason_codes=(),
                updated_at=received,
            )
            self._store.set_dead_man(restored)
            self._audit_record(
                "dead_man.restored",
                "OK",
                "dead-man-switch",
                None,
                None,
                "Core ↔ MT4 heartbeat restored",
            )
            self._emit(
                "system.emergency.heartbeat_restored",
                level=None,
                target=None,
                active=False,
                actor="dead-man-switch",
                reason="Core ↔ MT4 heartbeat restored",
                dead_man_switch=True,
            )
            self._alert(
                "DEAD_MAN_SWITCH_RESTORED",
                "INFO",
                "Core ↔ MT4 heartbeat restored — safe execution state cleared",
                "New entries remain governed by active emergency controls only.",
            )

    def check_dead_man(self, now: datetime | None = None) -> DeadManSwitchState:
        """Deterministic dead man evaluation; engages the safe execution state.

        Idempotent: a loss engages exactly once per episode; only a subsequent
        heartbeat clears it. Broker-side SL/TP are never touched and positions
        are never closed unless ``flatten_on_heartbeat_loss`` is explicitly set.
        """
        if not self._policy.dead_man_switch_enabled:
            return self._store.get_dead_man()
        now = now or self._clock.now()
        state = self._store.get_dead_man()
        if state.safe_execution_state:
            return state
        reference = self._last_heartbeat_at or self._armed_at
        if (now - reference) <= self._policy.heartbeat_timeout:
            return state
        engaged = DeadManSwitchState(
            dead_man_switch_enabled=self._policy.dead_man_switch_enabled,
            heartbeat_timeout_seconds=self._policy.heartbeat_timeout.total_seconds(),
            armed_at=self._armed_at,
            last_heartbeat_at=self._last_heartbeat_at,
            safe_execution_state=True,
            heartbeat_lost_at=now,
            reason_codes=(DeadManSwitchReason.HEARTBEAT_LOST.value,),
            updated_at=now,
        )
        stored = self._store.set_dead_man(engaged)
        detail = (
            "Core ↔ MT4 heartbeat lost: safe execution state active. Broker-side "
            "SL/TP remain untouched; new entries are blocked. Positions are NOT "
            "closed automatically by connectivity loss."
            + (
                " flatten_on_heartbeat_loss is enabled — closing positions now."
                if self._policy.flatten_on_heartbeat_loss
                else ""
            )
        )
        self._audit_record("dead_man.engaged", "OK", "dead-man-switch", None, None, detail)
        self._emit(
            "system.emergency.heartbeat_lost",
            level=None,
            target=None,
            active=True,
            actor="dead-man-switch",
            reason="Core ↔ MT4 heartbeat lost",
            dead_man_switch=True,
            safe_execution_state=True,
        )
        self._alert("DEAD_MAN_SWITCH_ENGAGED", "CRITICAL", "Core ↔ MT4 heartbeat lost", detail)
        if self._policy.flatten_on_heartbeat_loss and self._flattener is not None:
            closed = self._flattener(reason="dead man switch: heartbeat lost")
            self._audit_record(
                "dead_man.flatten",
                "OK",
                "dead-man-switch",
                None,
                None,
                ", ".join(closed) if closed else "no open positions",
            )
        return stored

    # ── Emergency close authorization (INV-1: deterministic code decides) ─
    def assert_emergency_close_authorized(self, intent: OrderIntent) -> None:
        """Deterministic authorization for emergency-generated closure intents."""
        if intent.strategy_id != EMERGENCY_STRATEGY_ID:
            raise EmergencyControlViolation(("NOT_AN_EMERGENCY_CLOSURE",))
        if not (self.emergency_kill_active() or self.safe_execution_state_active()):
            raise EmergencyControlViolation(("NO_EMERGENCY_ACTIVE",))
        if not (self._policy.flatten_on_emergency_kill or self._policy.flatten_on_heartbeat_loss):
            raise EmergencyControlViolation(("FLATTEN_NOT_CONFIGURED",))

    def assert_mutation_authorized(self) -> None:
        """Order mutations (cancel/modify) at a live venue require an active
        EMERGENCY_KILL — deterministic, LLM-free (INV-1, ADR-0025)."""
        if not self.emergency_kill_active():
            raise EmergencyControlViolation(("NO_EMERGENCY_ACTIVE",))

    # ── Side effects ──────────────────────────────────────────────────────
    def _run_emergency_side_effects(self, reason: str) -> None:
        if self._policy.cancel_pending_on_emergency_kill and self._pending_canceller is not None:
            cancelled = self._pending_canceller(reason=f"emergency kill: {reason}")
            self._audit_record(
                "emergency.cancel_pending",
                "OK",
                "emergency-controller",
                None,
                EmergencyLevel.EMERGENCY_KILL,
                ", ".join(cancelled) if cancelled else "no pending orders",
            )
        if self._policy.flatten_on_emergency_kill and self._flattener is not None:
            flattened = self._flattener(reason=f"emergency kill: {reason}")
            self._audit_record(
                "emergency.flatten",
                "OK",
                "emergency-controller",
                None,
                EmergencyLevel.EMERGENCY_KILL,
                ", ".join(flattened) if flattened else "no open positions",
            )

    # ── Validation ────────────────────────────────────────────────────────
    @staticmethod
    def _validate_target(level: EmergencyLevel, target: str | None) -> None:
        if level in _TARGETED_LEVELS and not target:
            raise ValueError(f"{level.value} requires a target")
        if level not in _TARGETED_LEVELS and target:
            raise ValueError(f"{level.value} does not accept a target")

    # ── Emission helpers ──────────────────────────────────────────────────
    def _emit(
        self,
        event_name: str,
        *,
        level: EmergencyLevel | None,
        target: str | None,
        active: bool,
        actor: str,
        reason: str,
        dead_man_switch: bool = False,
        safe_execution_state: bool = False,
    ) -> None:
        if self._events is None:
            return
        now = self._clock.now()
        payload = EmergencyEvent(
            trace_id=None,
            produced_at=now,
            provenance=build_provenance(self._producer, now),
            level=level,
            target=target,
            active=active,
            actor=actor,
            reason=reason,
            dead_man_switch=dead_man_switch,
            safe_execution_state=safe_execution_state,
        )
        self._events.emit(make_event(event_name, payload, self._clock, producer=self._producer))

    def _audit_record(
        self,
        action: str,
        outcome: str,
        actor: str,
        target: str | None,
        level: EmergencyLevel | None,
        detail: str,
    ) -> None:
        if self._audit is None:
            return
        self._audit.record(
            action,
            actor=actor,
            target=target or (level.value if level is not None else "dead-man-switch"),
            outcome=outcome,
            metadata={"level": level.value if level is not None else None, "detail": detail},
        )

    def _alert(
        self,
        kind: str,
        severity: Literal["CRITICAL", "WARNING", "INFO"],
        title: str,
        detail: str,
    ) -> None:
        if self._alerts is None:
            return
        self._alerts.raise_alert(
            OperationalAlert(
                alert_id=uuid4(),
                kind=kind,
                severity=severity,
                title=title,
                detail=detail,
                raised_at=self._clock.now(),
            )
        )


def assert_emergency_closure_matches_positions(
    positions: Iterable[ExecutionPosition], intent: OrderIntent
) -> None:
    """An emergency intent may only close a known open position (ADR-0025).

    Deterministic structural check used by the live-runtime authorizer on top
    of :meth:`EmergencyController.assert_emergency_close_authorized`: the intent
    must be a MARKET order whose side offsets an open position of the same
    instrument with exactly the position's quantity. Anything else — e.g. a
    BUY tagged ``CORE-EMERGENCY`` with no matching short — is refused.
    """
    if intent.order_type is not OrderType.MARKET:
        raise EmergencyControlViolation(("NOT_A_MARKET_CLOSURE",))
    for position in positions:
        if position.instrument_id != intent.instrument_id:
            continue
        offsetting_side = OrderSide.SELL if position.side is PositionSide.LONG else OrderSide.BUY
        if intent.side is offsetting_side and intent.quantity == position.quantity:
            return
    raise EmergencyControlViolation(("INTENT_DOES_NOT_CLOSE_AN_OPEN_POSITION",))
