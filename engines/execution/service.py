"""Execution service: submit path and the mandatory startup reconciliation.

The submit path honors INV-6 end to end:

1. SAFE_MODE gate (no new positions while active);
2. persist ``ORDER_INTENT`` and then ``SUBMITTED`` **before** the wire send —
   a crash at any point leaves authoritative state in PostgreSQL;
3. apply the venue reply and pushed events through the applier (duplicate /
   out-of-order tolerant).

``startup_reconciliation`` is the §9 restart procedure, in order:

1. load persisted state;
2. query MT4 (broker state);
3. compare open orders;
4. compare positions;
5. compare quantities;
6. compare identifiers;
7. reconcile differences — material unexplained ones flip SAFE_MODE.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid4

from adapters.mt4.errors import Mt4ProtocolError
from adapters.mt4.protocol import (
    FillEvent,
    HeartbeatEvent,
    OrderAck,
    OrderReject,
    PartialFillEvent,
    PositionSnapshotEvent,
    ReconciliationResponse,
    WireMessage,
)
from adapters.mt4.transport import ConnectionHealth
from core.audit.audit import AuditLogger
from core.clock.clocks import Clock
from core.domain.enums import (
    DiscrepancyCode,
    OperatingMode,
    OrderSide,
    OrderType,
    PositionSide,
    SafeModeAction,
    SafeModeReason,
)
from core.observability.metrics import OperationalMetrics, metrics
from core.schemas.base import Provenance
from core.schemas.execution import (
    LIVE_ORDER_STATES,
    ExecutionPosition,
    OrderRecord,
    ReconciliationDiscrepancy,
    ReconciliationEvent,
    ReconciliationRun,
    StartupOutcome,
)
from core.schemas.trading import OrderIntent, RiskDecision

from engines.execution.applier import ExecutionDivergenceError, OrderStateApplier
from engines.execution.emergency import EMERGENCY_STRATEGY_ID, EmergencyController
from engines.execution.events import EventSink, make_event
from engines.execution.live_gate import HumanApprovalGate, LiveGateViolation, PriceContext
from engines.execution.persistence import ExecutionStateStore
from engines.execution.reconciler import BrokerReconciler, BrokerView, VenueViewPosition
from engines.execution.safe_mode import SafeModeController
from engines.live_auto.registry import LiveAutoRegistry

__all__ = ["ExecutionService", "ReconcileClient"]


class ReconcileClient(Protocol):
    """Structural view of the MT4 execution client (satisfied by
    :class:`adapters.mt4.client.Mt4ExecutionClient` and by test doubles)."""

    def submit_order(
        self,
        *,
        order_intent_id: UUID,
        strategy_id: str,
        strategy_version: str,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        order_type: OrderType,
        price: Decimal | None = None,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
        max_slippage: Decimal = Decimal("0"),
        expires_at: datetime | None = None,
        trace_id: UUID | None = None,
        live_intent: OrderIntent | None = None,
    ) -> OrderAck | OrderReject: ...

    def cancel_order(
        self,
        *,
        order_intent_id: UUID,
        strategy_id: str,
        strategy_version: str,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        order_type: OrderType,
        reason: str | None = None,
        trace_id: UUID | None = None,
    ) -> OrderAck | OrderReject: ...

    def reconcile(self, *, strategy_id: str = "CORE") -> ReconciliationResponse: ...

    def resync_sequences(self, mapping: dict[str, int]) -> None: ...

    def connection_health(self) -> ConnectionHealth: ...

    def drain_events(self, timeout_ms: int = 50) -> list[WireMessage]: ...


class ExecutionService:
    """Owns the submit path and the restart reconciliation procedure."""

    def __init__(
        self,
        *,
        store: ExecutionStateStore,
        applier: OrderStateApplier,
        reconciler: BrokerReconciler,
        controller: SafeModeController,
        client: ReconcileClient,
        clock: Clock,
        audit: AuditLogger | None = None,
        events: EventSink | None = None,
        producer: str = "execution-engine",
        operational_metrics: OperationalMetrics | None = None,
        live_gate: HumanApprovalGate | None = None,
        operating_mode: OperatingMode = OperatingMode.PAPER,
        emergency: EmergencyController | None = None,
        live_auto: LiveAutoRegistry | None = None,
    ) -> None:
        if operating_mode is OperatingMode.LIVE_GATED and live_gate is None:
            raise ValueError("LIVE_GATED execution service requires a human approval gate")
        if operating_mode is OperatingMode.LIVE_AUTO and live_auto is None:
            raise ValueError(
                "LIVE_AUTO execution service requires the deterministic live-auto registry"
            )
        self._store = store
        self._applier = applier
        self._reconciler = reconciler
        self._controller = controller
        self._client = client
        self._clock = clock
        self._audit = audit
        self._events = events
        self._producer = producer
        self._metrics = operational_metrics or metrics
        self._live_gate = live_gate
        self._operating_mode = operating_mode
        self._emergency = emergency
        self._live_auto = live_auto

    # ── Submit path ───────────────────────────────────────────────────────
    def submit(
        self,
        intent: OrderIntent,
        *,
        venue: str = "mt4",
        price_context: PriceContext | None = None,
        risk_decision: RiskDecision | None = None,
    ) -> OrderRecord:
        """Run the intent through the gates, persist before send, apply reply."""
        began = time.perf_counter()
        self.check_emergency()
        if self._emergency is not None:
            self._emergency.assert_can_enter(intent.strategy_id, intent.instrument_id)
        self._controller.assert_allowed(SafeModeAction.NEW_ENTRY)
        if intent.operating_mode is not self._operating_mode:
            raise LiveGateViolation(
                "OrderIntent mode does not match the authoritative execution mode"
            )
        live_approval = None
        live_auto_authorized = False
        if intent.operating_mode is OperatingMode.LIVE_GATED:
            if self._live_gate is None or price_context is None:
                raise LiveGateViolation("explicit human approval is required")
            live_approval = self._live_gate.consume(intent, price_context)
        elif intent.operating_mode is OperatingMode.LIVE_AUTO:
            # Automated execution: the deterministic live-auto registry is the
            # gate. Risk Engine + strategy lifecycle state + budgets + loss
            # limit + emergency controls must all hold (Phase 11).
            if self._live_auto is None or risk_decision is None or price_context is None:
                raise LiveGateViolation(
                    "LIVE_AUTO requires the live-auto registry, a Risk Engine "
                    "decision and a fresh quote"
                )
            self._live_auto.assert_submission_authorized(
                intent=intent, risk_decision=risk_decision, price_context=price_context
            )
            live_auto_authorized = True
        self._applier.record_order_intent(intent, venue=venue)
        # Persist SUBMITTED before the wire send: crash-after-submit safety.
        self._applier.record_submitted(intent.order_intent_id)
        reply = self._client.submit_order(
            order_intent_id=intent.order_intent_id,
            strategy_id=intent.strategy_id,
            strategy_version=intent.strategy_version,
            symbol=intent.instrument_id,
            side=intent.side,
            quantity=intent.quantity,
            order_type=intent.order_type,
            price=intent.price,
            stop_loss=intent.stop_loss,
            take_profit=intent.take_profit,
            max_slippage=intent.max_slippage,
            expires_at=(
                live_approval.expires_at if live_approval is not None else intent.valid_until
            ),
            trace_id=intent.trace_id,
            live_intent=intent if (live_approval is not None or live_auto_authorized) else None,
        )
        if isinstance(reply, OrderAck):
            self._apply_ack(intent.order_intent_id, reply)
        elif isinstance(reply, OrderReject):
            self._applier.record_rejected(
                intent.order_intent_id,
                reason=reply.error.code.value,
                event_id=str(reply.message_id),
            )
            self._metrics.observe_execution("rejected", time.perf_counter() - began)
        else:  # pragma: no cover — the client only returns Ack/Reject
            raise RuntimeError(f"unexpected submit reply {type(reply).__name__}")
        self.drain_events(timeout_ms=0)
        record = self._store.get_order(intent.order_intent_id)
        if record is None:  # pragma: no cover — applier guarantees existence
            raise RuntimeError(f"order {intent.order_intent_id} vanished from the store")
        return record

    def _apply_ack(self, order_intent_id: UUID, reply: OrderAck) -> None:
        if reply.status == "CANCELLED":
            self._applier.record_cancelled(order_intent_id, event_id=str(reply.message_id))
        else:
            # SUBMITTED / ACKNOWLEDGED / FILLED / MODIFIED all mean the venue
            # holds the order; fills arrive as pushed events.
            self._applier.record_acknowledged(
                order_intent_id,
                venue_order_id=reply.venue_order_id,
                event_id=str(reply.message_id),
            )

    # ── Event pump ────────────────────────────────────────────────────────
    def drain_events(self, *, timeout_ms: int = 0) -> tuple[WireMessage, ...]:
        """Apply pushed venue events. Divergences escalate to SAFE_MODE."""
        drained = tuple(self._client.drain_events(timeout_ms=timeout_ms))
        for event in drained:
            if isinstance(event, HeartbeatEvent) and self._emergency is not None:
                self._emergency.on_heartbeat(event.timestamp)
                continue
            try:
                self._apply_event(event)
            except ExecutionDivergenceError as exc:
                self._on_divergence(exc)
                raise
            except ValueError:
                # Stale/unknown frames — audited and skipped, never fatal.
                self._audit_note("execution.event.skipped", str(event.message_type))
        self.check_emergency()
        return drained

    def _apply_event(self, event: WireMessage) -> None:
        if isinstance(event, PartialFillEvent):
            self._applier.record_partial_fill(
                event.order_intent_id,
                event_id=f"{event.message_id}:{event.sequence}",
                sequence=event.sequence,
                filled_quantity=event.filled_quantity,
                average_fill_price=event.average_fill_price,
                venue_order_id=event.venue_order_id,
                commission=event.commission,
                slippage=event.slippage,
            )
        elif isinstance(event, FillEvent):
            event_id = f"{event.message_id}:{event.sequence}"
            before = self._store.get_order(event.order_intent_id)
            if before is not None and event_id in before.processed_event_ids:
                return
            received_at = self._clock.now()
            self._applier.record_fill(
                event.order_intent_id,
                event_id=event_id,
                sequence=event.sequence,
                filled_quantity=event.filled_quantity,
                average_fill_price=event.average_fill_price,
                venue_order_id=event.venue_order_id,
                commission=event.commission,
                slippage=event.slippage,
            )
            if before is not None and before.submitted_at is not None:
                self._metrics.observe_execution(
                    "filled", max(0.0, (received_at - before.submitted_at).total_seconds())
                )
        elif isinstance(event, PositionSnapshotEvent):
            for venue_position in event.positions:
                snapshot = venue_position.position
                self._store.upsert_position(
                    ExecutionPosition(
                        venue_position_id=venue_position.venue_position_id,
                        account_id=event.account_id,
                        instrument_id=snapshot.instrument_id,
                        side=snapshot.side,
                        quantity=snapshot.quantity,
                        average_entry_price=snapshot.average_entry_price,
                        order_intent_id=self._provenance_intent(snapshot.provenance.source_ids),
                        opened_at=snapshot.as_of,
                        updated_at=snapshot.as_of,
                    )
                )
        # Heartbeat / account snapshot events carry no order state.

    @staticmethod
    def _provenance_intent(source_ids: dict[str, str]) -> UUID | None:
        raw = source_ids.get("order_intent_id")
        if raw is None:
            return None
        try:
            return UUID(raw)
        except ValueError:
            return None

    def _on_divergence(self, exc: ExecutionDivergenceError) -> None:
        reason = (
            SafeModeReason.OVERFILL_DETECTED.value
            if exc.code is DiscrepancyCode.OVERFILL
            else SafeModeReason.RECONCILIATION_DIVERGENCE.value
        )
        self._controller.enter([reason], note=str(exc))
        self._audit_note("execution.divergence", f"{exc.code.value}: {exc}")

    # ── Emergency control system (INV-7) ─────────────────────────────────
    def check_emergency(self) -> None:
        """Deterministic dead man evaluation (idempotent; no-op when unwired)."""
        if self._emergency is None:
            return
        self._emergency.check_dead_man(self._clock.now())

    def cancel_pending_orders(self, *, reason: str) -> list[str]:
        """``CANCEL_PENDING`` executor: cancel every still-live order at the venue.

        Only reachable through the emergency controller during EMERGENCY_KILL;
        every cancellation is persisted through the applier and audited.
        """
        if self._emergency is None or not self._emergency.emergency_kill_active():
            raise LiveGateViolation("pending-order cancellation requires an active EMERGENCY_KILL")
        cancelled: list[str] = []
        for record in self._store.list_orders():
            if record.state not in LIVE_ORDER_STATES:
                continue
            reply = self._client.cancel_order(
                order_intent_id=record.order_intent_id,
                strategy_id=record.strategy_id,
                strategy_version=record.strategy_version,
                symbol=record.instrument_id,
                side=record.side,
                quantity=record.requested_quantity,
                order_type=record.order_type,
                reason=reason,
            )
            if isinstance(reply, OrderAck):
                self._applier.record_cancelled(
                    record.order_intent_id, event_id=str(reply.message_id)
                )
            cancelled.append(str(record.order_intent_id))
            self._audit_note(
                "emergency.cancel_pending",
                f"order {record.order_intent_id} cancelled — {reason}",
            )
        return cancelled

    def flatten_positions(self, *, reason: str) -> list[str]:
        """``OPTIONALLY_FLATTEN`` executor: close every open position.

        Only reachable through the emergency controller when the policy
        explicitly enables flattening (``flatten_on_emergency_kill`` or
        ``flatten_on_heartbeat_loss``). Closures are risk-reducing offsetting
        MARKET orders stamped with :data:`EMERGENCY_STRATEGY_ID`; they bypass
        the human approval gate but are authorized deterministically by
        :meth:`EmergencyController.assert_emergency_close_authorized` and
        remain fully persisted, audited and reconciled (INV-1, INV-6).
        """
        if self._emergency is None or not (
            self._emergency.emergency_kill_active() or self._emergency.safe_execution_state_active()
        ):
            raise LiveGateViolation(
                "position flattening requires an active emergency (kill or dead man safe state)"
            )
        flattened: list[str] = []
        now = self._clock.now()
        for position in self._store.list_positions(open_only=True):
            side = OrderSide.SELL if position.side is PositionSide.LONG else OrderSide.BUY
            intent = OrderIntent(
                order_intent_id=uuid4(),
                # Emergency closures are not risk-engined: they are risk-reducing
                # by construction. The id is minted here so INV-2 still holds.
                risk_decision_id=uuid4(),
                strategy_id=EMERGENCY_STRATEGY_ID,
                strategy_version="CORE",
                instrument_id=position.instrument_id,
                operating_mode=self._operating_mode,
                side=side,
                order_type=OrderType.MARKET,
                quantity=position.quantity,
                created_by="emergency-controller",
                produced_at=now,
                provenance=Provenance(producer="emergency-controller", produced_at=now),
            )
            self._applier.record_order_intent(intent, venue="mt4")
            self._applier.record_submitted(intent.order_intent_id)
            reply = self._client.submit_order(
                order_intent_id=intent.order_intent_id,
                strategy_id=intent.strategy_id,
                strategy_version=intent.strategy_version,
                symbol=intent.instrument_id,
                side=side,
                quantity=position.quantity,
                order_type=OrderType.MARKET,
                expires_at=self._clock.now() + timedelta(seconds=30),
                trace_id=None,
                live_intent=intent
                if self._operating_mode in (OperatingMode.LIVE_GATED, OperatingMode.LIVE_AUTO)
                else None,
            )
            if isinstance(reply, OrderAck):
                self._apply_ack(intent.order_intent_id, reply)
            elif isinstance(reply, OrderReject):
                self._applier.record_rejected(
                    intent.order_intent_id,
                    reason=reply.error.code.value,
                    event_id=str(reply.message_id),
                )
            flattened.append(position.venue_position_id)
            self._audit_note(
                "emergency.flatten",
                f"position {position.venue_position_id} closed — {reason}",
            )
        return flattened

    # ── Startup reconciliation (§9 restart procedure) ─────────────────────
    def startup_reconciliation(self) -> StartupOutcome:
        """The mandatory 7-step restart comparison against live broker state."""
        started_at = self._clock.now()
        self.check_emergency()
        safe_mode_before = self._store.get_safe_mode()

        # 1. Load persisted state (authoritative even across a crash).
        persisted_orders = self._store.list_orders()
        persisted_positions = self._store.list_positions(open_only=True)
        _ = persisted_orders, persisted_positions

        # 2. Query MT4.
        try:
            response = self._client.reconcile()
        except Mt4ProtocolError as exc:
            run = self._record_unreachable_run(started_at, str(exc))
            entered = self._controller.enter(
                [SafeModeReason.BROKER_UNREACHABLE.value],
                note=f"startup reconciliation could not reach the broker: {exc}",
            )
            self._metrics.unexpected_broker_positions.set(0)
            self._emit_reconciliation_event(run, divergence=True)
            return StartupOutcome(
                run_id=run.run_id,
                broker_reachable=False,
                safe_mode_active=True,
                safe_mode_reason_codes=entered.reason_codes,
                material_discrepancies=run.material_discrepancies,
                orders_reconciled=run.orders_reconciled,
            )

        view = self._broker_view(response)

        # 3-6. Compare open orders, positions, quantities and identifiers,
        # then reconcile explainable differences (applies store mutations).
        run = self._reconciler.reconcile(view)

        # 7. Adopt bridge-side sequences so the next commands continue cleanly.
        self._client.resync_sequences(view.last_sequences)

        if run.material_discrepancies > 0:
            codes = sorted({d.code.value for d in run.discrepancies if d.severity == "MATERIAL"})
            entered = self._controller.enter(
                [SafeModeReason.RECONCILIATION_DIVERGENCE.value],
                note=f"material discrepancies at startup: {', '.join(codes)}",
            )
            run = run.model_copy(update={"safe_mode_entered": True})
        else:
            exited = self._controller.exit(note="clean startup reconciliation")
            run = run.model_copy(
                update={"safe_mode_exited": exited.active is False and safe_mode_before.active}
            )
        self._store.save_reconciliation_run(run)
        unexpected_positions = sum(
            1
            for discrepancy in run.discrepancies
            if discrepancy.code is DiscrepancyCode.UNEXPECTED_BROKER_POSITION
        )
        self._metrics.unexpected_broker_positions.set(unexpected_positions)
        self._emit_reconciliation_event(run, divergence=run.material_discrepancies > 0)
        self._audit_note(
            "reconciliation.run",
            f"run {run.run_id}: {run.material_discrepancies} material, "
            f"{run.orders_resolved} resolved",
        )
        return StartupOutcome(
            run_id=run.run_id,
            broker_reachable=True,
            safe_mode_active=self._controller.active,
            safe_mode_reason_codes=self._store.get_safe_mode().reason_codes,
            material_discrepancies=run.material_discrepancies,
            orders_reconciled=run.orders_reconciled,
        )

    def _record_unreachable_run(self, started_at: datetime, detail: str) -> ReconciliationRun:
        run = ReconciliationRun(
            run_id=uuid4(),
            started_at=started_at,
            compared_at=self._clock.now(),
            broker_reachable=False,
            broker_connected=False,
            discrepancies=(
                ReconciliationDiscrepancy(
                    code=DiscrepancyCode.BROKER_UNREACHABLE,
                    severity="MATERIAL",
                    explanation=f"broker unreachable during startup reconciliation: {detail}",
                ),
            ),
            material_discrepancies=1,
        )
        return self._store.save_reconciliation_run(run)

    def _broker_view(self, response: ReconciliationResponse) -> BrokerView:
        positions: list[VenueViewPosition] = []
        for venue_position in response.positions:
            snapshot = venue_position.position
            positions.append(
                VenueViewPosition(
                    venue_position_id=venue_position.venue_position_id,
                    magic=venue_position.magic,
                    account_id=snapshot.account_id,
                    strategy_id=snapshot.strategy_id,
                    instrument_id=snapshot.instrument_id,
                    side=snapshot.side,
                    quantity=snapshot.quantity,
                    average_entry_price=snapshot.average_entry_price,
                    order_intent_id=self._provenance_intent(snapshot.provenance.source_ids),
                )
            )
        account = response.account.model_dump(mode="json") if response.account is not None else None
        return BrokerView(
            account=account,
            positions=tuple(positions),
            open_order_intent_ids=response.open_order_intent_ids,
            broker_connected=response.broker_connected,
            trading_enabled=response.trading_enabled,
            last_sequences=response.last_sequences,
        )

    # ── Emission helpers ──────────────────────────────────────────────────
    def _emit_reconciliation_event(self, run: ReconciliationRun, *, divergence: bool) -> None:
        if self._events is None:
            return
        now = self._clock.now()
        payload = ReconciliationEvent(
            trace_id=None,
            produced_at=now,
            provenance=Provenance(producer=self._producer, produced_at=now),
            run_id=run.run_id,
            material_discrepancies=run.material_discrepancies,
            safe_mode_entered=run.safe_mode_entered,
            orders_reconciled=run.orders_reconciled,
            discrepancy_codes=sorted(d.code.value for d in run.discrepancies),
        )
        event_name = "reconciliation.divergence" if divergence else "order.reconciled"
        self._events.emit(make_event(event_name, payload, self._clock, producer=self._producer))

    def _audit_note(self, action: str, detail: str) -> None:
        if self._audit is None:
            return
        self._audit.record(
            action,
            actor="execution-service",
            target="execution",
            outcome="OK",
            metadata={"detail": detail},
        )
