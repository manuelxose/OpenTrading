"""Production composition root for the live MT4 execution boundary.

Supports both live operating modes:

- ``LIVE_GATED`` — every order requires a consumed human approval;
- ``LIVE_AUTO``  — promoted strategies trade without per-trade approval, but
  every order still passes the deterministic live-auto registry (Risk Engine,
  lifecycle state, budgets, loss limit), the emergency/kill-switch controls
  and the MT4 local safety checks (Phase 11). Disabled by default.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from adapters.mt4.client import Mt4ExecutionClient
from adapters.mt4.config import Mt4Settings, get_mt4_settings
from adapters.mt4.protocol import CommandMessage
from adapters.mt4.transport import Mt4Endpoints
from core.audit.audit import AuditLogger
from core.audit.persistence import PostgresAuditSink
from core.clock.clocks import Clock, SystemClock
from core.config.settings import Settings
from core.domain.enums import OperatingMode
from core.schemas.execution import LIVE_ORDER_STATES
from core.schemas.trading import OrderIntent

from engines.execution.applier import OrderStateApplier
from engines.execution.emergency import (
    EMERGENCY_STRATEGY_ID,
    EmergencyController,
    EmergencyPolicy,
    assert_emergency_closure_matches_positions,
)
from engines.execution.emergency_persistence import PostgresEmergencyStore
from engines.execution.live_gate import HumanApprovalGate, LiveGateConfig, LiveGateViolation
from engines.execution.live_gate_persistence import PostgresApprovalStore
from engines.execution.persistence import PostgresExecutionStateStore
from engines.execution.reconciler import BrokerReconciler
from engines.execution.safe_mode import InMemoryAlertSink, SafeModeController
from engines.execution.service import ExecutionService
from engines.live_auto.config import LiveAutoConfig
from engines.live_auto.persistence import PostgresLiveAutoStore
from engines.live_auto.registry import LiveAutoRegistry

__all__ = ["LiveExecutionRuntime", "build_live_execution_runtime"]


@dataclass(frozen=True, slots=True)
class LiveExecutionRuntime:
    gate: HumanApprovalGate | None
    client: Mt4ExecutionClient
    service: ExecutionService
    emergency: EmergencyController
    live_auto: LiveAutoRegistry | None = None

    def connect_and_reconcile(self) -> None:
        self.client.connect()
        self.service.startup_reconciliation()

    def check_emergency(self) -> None:
        """Deterministic dead man evaluation (safe to call on a cadence)."""
        self.service.check_emergency()

    def close(self) -> None:
        self.client.close()


def build_live_execution_runtime(
    settings: Settings,
    *,
    clock: Clock | None = None,
    mt4: Mt4Settings | None = None,
) -> LiveExecutionRuntime:
    """Build the only supported live Core→MT4 compositions; fail closed.

    ``LIVE_GATED`` requires the approval signing key; ``LIVE_AUTO`` requires
    the live-auto capability to be enabled with every limit explicitly set —
    anything else raises before any socket or store is touched.
    """
    mode = settings.operating_mode
    if mode not in (OperatingMode.LIVE_GATED, OperatingMode.LIVE_AUTO):
        raise ValueError("live runtime requires OT_OPERATING_MODE=LIVE_GATED or LIVE_AUTO")
    if mode is OperatingMode.LIVE_GATED and settings.live_approval_signing_key is None:
        raise ValueError("LIVE_GATED requires OT_LIVE_APPROVAL_SIGNING_KEY")
    live_clock = clock or SystemClock()
    mt4_settings = mt4 or get_mt4_settings()
    store = PostgresExecutionStateStore(settings.postgres_dsn)
    approval_store = PostgresApprovalStore(settings.postgres_dsn)
    emergency_store = PostgresEmergencyStore(settings.postgres_dsn)
    # Immutable governance trail lands in PostgreSQL (migration 0001).
    audit = AuditLogger(PostgresAuditSink(settings.postgres_dsn), live_clock)
    alerts = InMemoryAlertSink()
    applier = OrderStateApplier(store, live_clock)
    controller = SafeModeController(store, live_clock, audit=audit, alerts=alerts)
    reconciler = BrokerReconciler(store, applier, live_clock)
    client_holder: list[Mt4ExecutionClient] = []
    service_holder: list[ExecutionService] = []
    emergency = EmergencyController(
        emergency_store,
        live_clock,
        policy=EmergencyPolicy(
            dead_man_switch_enabled=settings.emergency_dead_man_enabled,
            heartbeat_timeout=timedelta(seconds=settings.emergency_heartbeat_timeout_seconds),
            cancel_pending_on_emergency_kill=settings.emergency_cancel_pending_on_kill,
            flatten_on_emergency_kill=settings.emergency_flatten_on_kill,
            flatten_on_heartbeat_loss=settings.emergency_flatten_on_heartbeat_loss,
        ),
        audit=audit,
        alerts=alerts,
        pending_canceller=lambda *, reason: (
            service_holder[0].cancel_pending_orders(reason=reason) if service_holder else []
        ),
        flattener=lambda *, reason: (
            service_holder[0].flatten_positions(reason=reason) if service_holder else []
        ),
    )

    def attest_demo() -> bool:
        return bool(client_holder and client_holder[0].reconcile().account.is_demo)

    gate: HumanApprovalGate | None = None
    live_auto: LiveAutoRegistry | None = None
    if mode is OperatingMode.LIVE_GATED:
        signing_key = settings.live_approval_signing_key
        if signing_key is None:  # fail-closed check above guarantees it
            raise ValueError("LIVE_GATED requires OT_LIVE_APPROVAL_SIGNING_KEY")
        gate = HumanApprovalGate(
            store=approval_store,
            clock=live_clock,
            signing_key=signing_key.get_secret_value().encode(),
            config=LiveGateConfig(
                approval_ttl=timedelta(seconds=settings.live_approval_ttl_seconds),
                max_price_drift_bps=settings.live_max_price_drift_bps,
                max_quote_age=timedelta(seconds=settings.live_max_quote_age_seconds),
                broker_demo=settings.live_broker_demo,
                max_live_quantity=settings.live_max_quantity,
            ),
            audit=audit,
            demo_account_attestor=attest_demo if settings.live_broker_demo else None,
        )
    else:
        live_auto_config = LiveAutoConfig.from_settings(settings)
        # Fail closed: a disabled or under-configured LIVE_AUTO never wires up.
        live_auto_config.assert_enabled()
        live_auto = LiveAutoRegistry(
            PostgresLiveAutoStore(settings.postgres_dsn), live_auto_config, live_clock, audit=audit
        )

    def live_authorizer(intent: OrderIntent) -> None:
        """Deterministic boundary check (INV-1): emergency closures are
        authorized by the emergency policy *and* must structurally close a
        persisted open position; LIVE_GATED orders require a consumed human
        approval; LIVE_AUTO orders are re-verified against the registry."""
        if intent.strategy_id == EMERGENCY_STRATEGY_ID:
            emergency.assert_emergency_close_authorized(intent)
            assert_emergency_closure_matches_positions(store.list_positions(open_only=True), intent)
            return
        if live_auto is not None:
            live_auto.assert_wire_authorized(intent=intent)
            return
        assert gate is not None  # LIVE_GATED
        gate.assert_consumed_authorization(intent)

    def live_mutation_authorizer(command: CommandMessage) -> None:
        """Fail-closed mutation authorizer (ADR-0025): cancels/modifies at a
        live venue are allowed only during EMERGENCY_KILL and only when the
        command targets a known live order (same id, symbol, side, quantity)."""
        emergency.assert_mutation_authorized()
        for record in store.list_orders():
            if record.order_intent_id != command.order_intent_id:
                continue
            if (
                record.state in LIVE_ORDER_STATES
                and record.instrument_id == command.symbol
                and record.side is command.side
                and record.requested_quantity == command.quantity
            ):
                return
        raise LiveGateViolation("order mutation does not target a known live order")

    client = Mt4ExecutionClient(
        live_clock,
        endpoints=Mt4Endpoints(
            command_addr=mt4_settings.command_addr,
            events_addr=mt4_settings.events_addr,
            quotes_addr=mt4_settings.quotes_addr,
        ),
        request_timeout_seconds=mt4_settings.request_timeout_seconds,
        degraded_after_seconds=mt4_settings.degraded_after_seconds,
        down_after_seconds=mt4_settings.down_after_seconds,
        operating_mode=mode,
        live_authorizer=live_authorizer,
        live_mutation_authorizer=live_mutation_authorizer,
    )
    client_holder.append(client)
    service = ExecutionService(
        store=store,
        applier=applier,
        reconciler=reconciler,
        controller=controller,
        client=client,
        clock=live_clock,
        audit=audit,
        live_gate=gate,
        operating_mode=mode,
        emergency=emergency,
        live_auto=live_auto,
    )
    service_holder.append(service)
    return LiveExecutionRuntime(
        gate=gate, client=client, service=service, emergency=emergency, live_auto=live_auto
    )
