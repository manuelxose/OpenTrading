"""CLI entrypoints: ``python -m engines.execution.cli <command>``.

``reconcile-once``
    Runs the mandatory startup reconciliation (§9) against PostgreSQL and the
    MT4 bridge, prints the report, and exits:

    - 0 — clean reconciliation (no material discrepancies, not in SAFE_MODE);
    - 2 — broker unreachable or SAFE_MODE entered — let cron/systemd alert.

``check-emergency``
    Deterministic dead man evaluation (INV-7): drains heartbeat events, then
    evaluates the dead man switch. Safe to run on a cron/systemd-timer cadence;
    exit 2 when the safe execution state is active so ops tooling alerts on it.
"""

from __future__ import annotations

import sys
from datetime import timedelta

from adapters.mt4.client import Mt4ExecutionClient
from adapters.mt4.config import get_mt4_settings
from adapters.mt4.transport import Mt4Endpoints
from core.audit.audit import AuditLogger, InMemoryAuditSink
from core.clock.clocks import SystemClock
from core.config.settings import get_settings
from core.domain.enums import SafeModeReason
from core.security import install_redacting_logging

from engines.execution.applier import OrderStateApplier
from engines.execution.emergency import EmergencyController, EmergencyPolicy
from engines.execution.emergency_persistence import PostgresEmergencyStore
from engines.execution.events import InMemoryEventSink
from engines.execution.persistence import PostgresExecutionStateStore
from engines.execution.reconciler import BrokerReconciler
from engines.execution.safe_mode import InMemoryAlertSink, SafeModeController
from engines.execution.service import ExecutionService

__all__ = ["main"]


def main(argv: list[str] | None = None) -> int:
    install_redacting_logging()
    args = sys.argv[1:] if argv is None else argv
    command = args[0] if args else "reconcile-once"
    if command == "check-emergency":
        return _check_emergency()
    if command == "reconcile-once":
        return _reconcile_once()
    print(f"unknown command {command!r} (expected reconcile-once|check-emergency)", file=sys.stderr)
    return 2


def _check_emergency() -> int:
    """Dead man switch monitor: drain heartbeats, evaluate, alert via exit code."""
    settings = get_settings()
    mt4 = get_mt4_settings()
    clock = SystemClock()

    store = PostgresExecutionStateStore(settings.postgres_dsn)
    emergency_store = PostgresEmergencyStore(settings.postgres_dsn)
    audit = AuditLogger(InMemoryAuditSink(), clock)
    events = InMemoryEventSink()
    alerts = InMemoryAlertSink()
    controller = SafeModeController(store, clock, audit=audit, events=events, alerts=alerts)
    emergency = EmergencyController(
        emergency_store,
        clock,
        policy=EmergencyPolicy(
            dead_man_switch_enabled=settings.emergency_dead_man_enabled,
            heartbeat_timeout=timedelta(seconds=settings.emergency_heartbeat_timeout_seconds),
            cancel_pending_on_emergency_kill=settings.emergency_cancel_pending_on_kill,
            flatten_on_emergency_kill=settings.emergency_flatten_on_kill,
            flatten_on_heartbeat_loss=settings.emergency_flatten_on_heartbeat_loss,
        ),
        audit=audit,
        alerts=alerts,
    )
    applier = OrderStateApplier(store, clock)
    reconciler = BrokerReconciler(store, applier, clock)

    client = Mt4ExecutionClient(
        clock,
        endpoints=Mt4Endpoints(
            command_addr=mt4.command_addr,
            events_addr=mt4.events_addr,
            quotes_addr=mt4.quotes_addr,
        ),
        request_timeout_seconds=mt4.request_timeout_seconds,
        degraded_after_seconds=mt4.degraded_after_seconds,
        down_after_seconds=mt4.down_after_seconds,
    )
    client.connect()
    try:
        service = ExecutionService(
            store=store,
            applier=applier,
            reconciler=reconciler,
            controller=controller,
            client=client,
            clock=clock,
            audit=audit,
            events=events,
            emergency=emergency,
        )
        service.drain_events(timeout_ms=500)
        state = emergency.check_dead_man(clock.now())
    finally:
        client.close()

    print(
        f"dead man switch: enabled={state.dead_man_switch_enabled}, "
        f"safe_execution_state={state.safe_execution_state}, "
        f"last_heartbeat={state.last_heartbeat_at}, "
        f"reasons={','.join(state.reason_codes) or '-'}"
    )
    for alert in alerts.alerts:
        print(f"  alert [{alert.kind}/{alert.severity}]: {alert.title} — {alert.detail}")
    if state.safe_execution_state:
        print("exit 2: dead man switch engaged — safe execution state active")
        return 2
    return 0


def _reconcile_once() -> int:
    settings = get_settings()
    mt4 = get_mt4_settings()
    clock = SystemClock()

    store = PostgresExecutionStateStore(settings.postgres_dsn)
    audit = AuditLogger(InMemoryAuditSink(), clock)
    events = InMemoryEventSink()
    alerts = InMemoryAlertSink()
    controller = SafeModeController(store, clock, audit=audit, events=events, alerts=alerts)
    applier = OrderStateApplier(store, clock)
    reconciler = BrokerReconciler(store, applier, clock)

    client = Mt4ExecutionClient(
        clock,
        endpoints=Mt4Endpoints(
            command_addr=mt4.command_addr,
            events_addr=mt4.events_addr,
            quotes_addr=mt4.quotes_addr,
        ),
        request_timeout_seconds=mt4.request_timeout_seconds,
        degraded_after_seconds=mt4.degraded_after_seconds,
        down_after_seconds=mt4.down_after_seconds,
    )
    client.connect()
    try:
        service = ExecutionService(
            store=store,
            applier=applier,
            reconciler=reconciler,
            controller=controller,
            client=client,
            clock=clock,
            audit=audit,
            events=events,
        )
        outcome = service.startup_reconciliation()
    finally:
        client.close()

    print(
        f"reconciliation run {outcome.run_id}:\n"
        f"  broker_reachable={outcome.broker_reachable}\n"
        f"  material_discrepancies={outcome.material_discrepancies}\n"
        f"  orders_reconciled={outcome.orders_reconciled}\n"
        f"  safe_mode_active={outcome.safe_mode_active}"
    )
    for alert in alerts.alerts:
        print(f"  alert [{alert.kind}/{alert.severity}]: {alert.title} — {alert.detail}")

    if not outcome.broker_reachable or outcome.safe_mode_active:
        reasons = (
            ", ".join(outcome.safe_mode_reason_codes) or SafeModeReason.BROKER_UNREACHABLE.value
        )
        print(f"exit 2: broker unreachable or SAFE_MODE active — reasons: {reasons}")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
