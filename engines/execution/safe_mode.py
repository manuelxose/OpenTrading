"""SAFE_MODE controller and operational alerting (INV-6, INV-7, §10).

SAFE_MODE is the platform-wide consequence of an unexplained material
discrepancy:

- **prevents new positions** — ``NEW_ENTRY`` is rejected with a violation;
- **allows monitoring** — events and snapshots keep flowing;
- **allows reconciliation** — repeated passes may clear the divergence;
- **allows risk-reducing actions** — cancels and position reductions remain
  available (never size increases; those route through NEW_ENTRY gating).

Every entry/exit produces a persisted record, a canonical domain event, an
audit entry and an operational alert.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, Protocol
from uuid import uuid4

from core.audit.audit import AuditLogger
from core.clock.clocks import Clock
from core.domain.enums import SafeModeAction
from core.schemas.base import Provenance
from core.schemas.events import DomainEvent
from core.schemas.execution import SafeModeAlert, SafeModeEvent, SafeModeRecord

from engines.execution.events import EventSink
from engines.execution.persistence import ExecutionStateStore

__all__ = [
    "AlertSink",
    "InMemoryAlertSink",
    "SafeModeController",
    "SafeModeViolation",
]


class AlertSink(Protocol):
    """Operational alert fan-out (log, pager, webhook — transport later)."""

    def raise_alert(self, alert: SafeModeAlert) -> None: ...


class InMemoryAlertSink:
    """Collects alerts in-process (tests, short-lived tools)."""

    def __init__(self) -> None:
        self.alerts: list[SafeModeAlert] = []

    def raise_alert(self, alert: SafeModeAlert) -> None:
        self.alerts.append(alert)


class SafeModeViolation(RuntimeError):
    """Raised when an action is blocked while SAFE_MODE is active."""

    def __init__(self, action: SafeModeAction, reason_codes: Sequence[str]) -> None:
        codes = ", ".join(reason_codes) if reason_codes else "unspecified"
        super().__init__(f"action {action.value} is blocked in SAFE_MODE (reasons: {codes})")
        self.action = action
        self.reason_codes = tuple(reason_codes)


#: The only action class SAFE_MODE blocks: opening/increasing exposure.
_BLOCKED_ACTIONS = frozenset({SafeModeAction.NEW_ENTRY})


class SafeModeController:
    """Persists SAFE_MODE state and gates execution actions (INV-6, §10)."""

    def __init__(
        self,
        store: ExecutionStateStore,
        clock: Clock,
        *,
        audit: AuditLogger | None = None,
        events: EventSink | None = None,
        alerts: AlertSink | None = None,
        producer: str = "execution-engine",
    ) -> None:
        self._store = store
        self._clock = clock
        self._audit = audit
        self._events = events
        self._alerts = alerts
        self._producer = producer

    # ── State ─────────────────────────────────────────────────────────────
    @property
    def active(self) -> bool:
        return self._store.get_safe_mode().active

    def state(self) -> SafeModeRecord:
        return self._store.get_safe_mode()

    # ── Transitions ───────────────────────────────────────────────────────
    def enter(self, reason_codes: Sequence[str], *, note: str | None = None) -> SafeModeRecord:
        """Enter SAFE_MODE (idempotent). Emits event + audit + alert."""
        now = self._clock.now()
        current = self._store.get_safe_mode()
        merged = tuple(dict.fromkeys((*current.reason_codes, *reason_codes)))
        record = SafeModeRecord(
            active=True,
            since=current.since if current.active else now,
            reason_codes=merged,
            note=note or current.note,
            exited_at=None,
            updated_at=now,
        )
        stored = self._store.set_safe_mode(record)
        if not current.active:
            self._emit("system.safe_mode.entered", stored)
            self._audit_record("safe_mode.entered", "OK", note or ", ".join(merged))
            self._alert(
                "SAFE_MODE_ENTERED",
                "CRITICAL",
                "Platform entered SAFE_MODE — new positions blocked",
                note or ", ".join(merged),
            )
        return stored

    def exit(self, *, note: str | None = None) -> SafeModeRecord:
        """Exit SAFE_MODE after a clean reconciliation. Emits event + audit."""
        now = self._clock.now()
        current = self._store.get_safe_mode()
        if not current.active:
            return current
        record = SafeModeRecord(
            active=False,
            since=current.since,
            reason_codes=current.reason_codes,
            note=note or current.note,
            exited_at=now,
            updated_at=now,
        )
        stored = self._store.set_safe_mode(record)
        self._emit("system.safe_mode.exited", stored)
        self._audit_record("safe_mode.exited", "OK", note or "clean reconciliation")
        self._alert(
            "SAFE_MODE_EXITED",
            "INFO",
            "Platform exited SAFE_MODE",
            note or "clean reconciliation",
        )
        return stored

    # ── Gating ────────────────────────────────────────────────────────────
    def assert_allowed(self, action: SafeModeAction) -> None:
        """Raise :class:`SafeModeViolation` for blocked actions while active."""
        state = self._store.get_safe_mode()
        if state.active and action in _BLOCKED_ACTIONS:
            raise SafeModeViolation(action, state.reason_codes)

    def can_submit_new_entries(self) -> bool:
        return not self._store.get_safe_mode().active

    # ── Emission helpers ──────────────────────────────────────────────────
    def _emit(self, event_name: str, state: SafeModeRecord) -> None:
        if self._events is None:
            return
        payload = SafeModeEvent(
            trace_id=None,
            produced_at=state.updated_at,
            provenance=Provenance(
                producer=self._producer,
                produced_at=state.updated_at,
            ),
            active=state.active,
            reason_codes=list(state.reason_codes),
            note=state.note,
            since=state.since,
        )
        event = DomainEvent(
            event_id=uuid4(),
            trace_id=None,
            event_time=state.updated_at,
            ingested_at=state.updated_at,
            producer=self._producer,
            event_name=event_name,
            payload=payload.canonical_dict(),
            provenance={"payload_schema": "SafeModeEvent", "payload_schema_version": "1.0.0"},
        )
        self._events.emit(event)

    def _audit_record(self, action: str, outcome: str, detail: str) -> None:
        if self._audit is None:
            return
        self._audit.record(
            action,
            actor="safe-mode-controller",
            target="system.safe_mode",
            outcome=outcome,
            metadata={"detail": detail},
        )

    def _alert(
        self, kind: str, severity: Literal["CRITICAL", "WARNING", "INFO"], title: str, detail: str
    ) -> None:
        if self._alerts is None:
            return
        self._alerts.raise_alert(
            SafeModeAlert(
                alert_id=uuid4(),
                kind=kind,
                severity=severity,
                title=title,
                detail=detail,
                raised_at=self._clock.now(),
            )
        )
