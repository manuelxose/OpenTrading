"""Order lifecycle state applier — the only writer of ``OrderRecord`` state.

Design rules (INV-6):

- **Never assume ``send_order() == executed_trade``.** Every venue report goes
  through this applier and the canonical state machine in
  :mod:`core.domain.state_machines` — no hard-coded transitions anywhere else.
- **Restart-safe.** State is persisted *before* anything irreversible happens
  (SUBMITTED is written before the wire send), and every update is a
  compare-and-set on the record ``version``.
- **Duplicate-tolerant.** Venue events carry fingerprints (``event_id``); a
  fingerprint already in ``processed_event_ids`` is a no-op, so replayed or
  duplicated fills never double-count.
- **Out-of-order-tolerant.** A fill arriving before the ACK synthesizes the
  missing ``ACKNOWLEDGED`` transition atomically; late ACK/REJECT after a
  terminal state are no-ops. Capital-affecting contradictions (fill for a
  cancelled/rejected order, cumulative fill beyond requested) raise
  :class:`ExecutionDivergenceError` — callers escalate to SAFE_MODE.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from core.clock.clocks import Clock
from core.domain.enums import DiscrepancyCode, OrderSide, OrderState, OrderType
from core.domain.state_machines import (
    InvalidStateTransition,
    assert_valid_order_transition,
    is_valid_order_transition,
)
from core.schemas.execution import LIVE_ORDER_STATES, OrderRecord
from core.schemas.trading import OrderIntent

from engines.execution.persistence import ExecutionStateStore, StaleStateError

__all__ = ["ExecutionDivergenceError", "OrderStateApplier"]

#: Bounded number of processed-event fingerprints retained per order.
MAX_PROCESSED_EVENT_IDS = 64

#: States after which a late ACK / REJECT / CANCEL is a harmless stale event.
_STALE_ACK_STATES = frozenset(
    {OrderState.ACKNOWLEDGED, OrderState.PARTIALLY_FILLED, OrderState.FILLED}
)


class ExecutionDivergenceError(RuntimeError):
    """A venue report contradicts authoritative state in a capital-relevant way."""

    def __init__(
        self,
        code: DiscrepancyCode,
        message: str,
        *,
        order_intent_id: UUID | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.order_intent_id = order_intent_id


class OrderStateApplier:
    """Transitions persisted ``OrderRecord`` state through the canonical machine."""

    def __init__(
        self,
        store: ExecutionStateStore,
        clock: Clock,
        *,
        max_processed_event_ids: int = MAX_PROCESSED_EVENT_IDS,
    ) -> None:
        self._store = store
        self._clock = clock
        self._max_processed = max_processed_event_ids

    # ── Upstream pipeline stages (proposal → intent) ─────────────────────
    def record_candidate(
        self,
        *,
        order_intent_id: UUID,
        strategy_id: str,
        strategy_version: str,
        instrument_id: str,
        side: OrderSide,
        order_type: OrderType,
        requested_quantity: Decimal,
    ) -> OrderRecord:
        """Persist a CANDIDATE record before the risk gate runs (full lifecycle)."""
        now = self._clock.now()
        record = OrderRecord(
            order_intent_id=order_intent_id,
            state=OrderState.CANDIDATE,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            instrument_id=instrument_id,
            side=side,
            order_type=order_type,
            requested_quantity=requested_quantity,
            remaining_quantity=requested_quantity,
            version=1,
            created_at=now,
            updated_at=now,
        )
        return self._store.save_order(record)

    def record_risk_rejected(self, order_intent_id: UUID, reason: str) -> OrderRecord:
        return self._apply(
            order_intent_id,
            OrderState.RISK_REJECTED,
            updates={"reject_reason": reason},
        )

    def record_approved(self, order_intent_id: UUID) -> OrderRecord:
        return self._apply(order_intent_id, OrderState.APPROVED, updates={})

    def record_order_intent(self, intent: OrderIntent, *, venue: str) -> OrderRecord:
        """Persist the canonical crossing object (INV-2) as ORDER_INTENT."""
        current = self._store.get_order(intent.order_intent_id)
        now = self._clock.now()
        if current is None:
            record = OrderRecord(
                order_intent_id=intent.order_intent_id,
                state=OrderState.ORDER_INTENT,
                strategy_id=intent.strategy_id,
                strategy_version=intent.strategy_version,
                instrument_id=intent.instrument_id,
                venue=venue,
                side=intent.side,
                order_type=intent.order_type,
                requested_quantity=intent.quantity,
                remaining_quantity=intent.quantity,
                version=1,
                created_at=now,
                updated_at=now,
            )
            return self._store.save_order(record)
        if current.state is OrderState.ORDER_INTENT:
            return current  # already recorded (idempotent re-entry)
        return self._apply(
            intent.order_intent_id,
            OrderState.ORDER_INTENT,
            updates={
                "strategy_id": intent.strategy_id,
                "strategy_version": intent.strategy_version,
                "instrument_id": intent.instrument_id,
                "venue": venue,
                "side": intent.side,
                "order_type": intent.order_type,
                "requested_quantity": intent.quantity,
                "remaining_quantity": intent.quantity,
            },
        )

    # ── Execution stages (the persisted write-before-send contract) ──────
    def record_submitted(self, order_intent_id: UUID) -> OrderRecord:
        """Persist SUBMITTED **before** the wire send (crash-after-submit safety)."""
        current = self._store.get_order(order_intent_id)
        if current is not None and current.state is OrderState.SUBMITTED:
            return current  # idempotent retry of the same intent
        return self._apply(order_intent_id, OrderState.SUBMITTED, updates={})

    def record_acknowledged(
        self,
        order_intent_id: UUID,
        *,
        venue_order_id: str | None = None,
        event_id: str | None = None,
    ) -> OrderRecord:
        """Apply a broker ACK. Late ACKs after fill/cancel/reject are no-ops."""
        current = self._store.get_order(order_intent_id)
        if current is None:
            raise ValueError(f"unknown order_intent_id {order_intent_id}")
        if current.state in _STALE_ACK_STATES or current.state in (
            OrderState.CANCELLED,
            OrderState.REJECTED,
            OrderState.RECONCILED,
            OrderState.CLOSED,
            OrderState.REVIEWED,
        ):
            return current
        updates: dict[str, object] = {}
        if venue_order_id is not None:
            updates["venue_order_id"] = venue_order_id
        return self._apply(
            order_intent_id, OrderState.ACKNOWLEDGED, event_id=event_id, updates=updates
        )

    def record_cancelled(
        self,
        order_intent_id: UUID,
        *,
        event_id: str | None = None,
        note: str | None = None,
    ) -> OrderRecord:
        """Apply a venue-side cancel. A cancel after FILLED/REJECTED is stale."""
        current = self._store.get_order(order_intent_id)
        if current is None:
            raise ValueError(f"unknown order_intent_id {order_intent_id}")
        if current.state in (
            OrderState.FILLED,
            OrderState.REJECTED,
            OrderState.CANCELLED,
            OrderState.RECONCILED,
            OrderState.CLOSED,
            OrderState.REVIEWED,
        ):
            return current
        updates: dict[str, object] = {}
        if note is not None:
            updates["reconciliation_note"] = note
        return self._apply(
            order_intent_id, OrderState.CANCELLED, event_id=event_id, updates=updates
        )

    def record_rejected(
        self,
        order_intent_id: UUID,
        *,
        reason: str,
        event_id: str | None = None,
    ) -> OrderRecord:
        """Apply a venue reject. A reject after FILLED/CANCELLED is stale."""
        current = self._store.get_order(order_intent_id)
        if current is None:
            raise ValueError(f"unknown order_intent_id {order_intent_id}")
        if current.state in (
            OrderState.FILLED,
            OrderState.CANCELLED,
            OrderState.REJECTED,
            OrderState.RECONCILED,
            OrderState.CLOSED,
            OrderState.REVIEWED,
        ):
            return current
        return self._apply(
            order_intent_id,
            OrderState.REJECTED,
            event_id=event_id,
            updates={"reject_reason": reason},
        )

    def record_partial_fill(
        self,
        order_intent_id: UUID,
        *,
        event_id: str,
        sequence: int,
        filled_quantity: Decimal,
        average_fill_price: Decimal,
        venue_order_id: str | None = None,
        commission: Decimal = Decimal("0"),
        slippage: Decimal | None = None,
    ) -> OrderRecord:
        """Apply one incremental partial fill (duplicate-safe)."""
        return self._record_fill(
            order_intent_id,
            event_id=event_id,
            sequence=sequence,
            filled_quantity=filled_quantity,
            average_fill_price=average_fill_price,
            venue_order_id=venue_order_id,
            commission=commission,
            slippage=slippage,
            venue_position_id=None,
        )

    def record_fill(
        self,
        order_intent_id: UUID,
        *,
        event_id: str,
        sequence: int,
        filled_quantity: Decimal,
        average_fill_price: Decimal,
        venue_order_id: str | None = None,
        venue_position_id: str | None = None,
        commission: Decimal = Decimal("0"),
        slippage: Decimal | None = None,
    ) -> OrderRecord:
        """Apply one incremental fill. Fill-before-ACK synthesizes the ACK."""
        return self._record_fill(
            order_intent_id,
            event_id=event_id,
            sequence=sequence,
            filled_quantity=filled_quantity,
            average_fill_price=average_fill_price,
            venue_order_id=venue_order_id,
            commission=commission,
            slippage=slippage,
            venue_position_id=venue_position_id,
        )

    # ── Reconciliation-driven healing (no venue events involved) ─────────
    def heal_acknowledged(self, order_intent_id: UUID, *, note: str) -> OrderRecord:
        """Reconciler: venue reports the order open but the ACK was never seen."""
        current = self._store.get_order(order_intent_id)
        if current is None:
            raise ValueError(f"unknown order_intent_id {order_intent_id}")
        if current.state is OrderState.SUBMITTED:
            return self._apply(
                order_intent_id,
                OrderState.ACKNOWLEDGED,
                updates={"reconciliation_note": note},
            )
        return current

    def heal_fill(
        self,
        order_intent_id: UUID,
        *,
        venue_position_id: str,
        quantity: Decimal,
        average_fill_price: Decimal,
        note: str,
    ) -> OrderRecord:
        """Reconciler: a broker position proves the fill happened (events lost)."""
        self._record_fill(
            order_intent_id,
            event_id=None,
            sequence=0,
            filled_quantity=quantity,
            average_fill_price=average_fill_price,
            venue_order_id=None,
            commission=Decimal("0"),
            slippage=None,
            venue_position_id=venue_position_id,
        )
        return self._update_fields(order_intent_id, {"reconciliation_note": note})

    def adopt_position(
        self,
        order_intent_id: UUID,
        *,
        venue_position_id: str,
        note: str,
    ) -> OrderRecord:
        """Reconciler: link a FILLED order to its venue position id (no transition)."""
        return self._update_fields(
            order_intent_id,
            {"venue_position_id": venue_position_id, "reconciliation_note": note},
        )

    def mark_reconciled(self, order_intent_id: UUID, *, note: str) -> OrderRecord:
        """Reconciler: a terminal order is consistent with the venue view."""
        current = self._store.get_order(order_intent_id)
        if current is None:
            raise ValueError(f"unknown order_intent_id {order_intent_id}")
        if current.state in (OrderState.RECONCILED, OrderState.CLOSED, OrderState.REVIEWED):
            return current
        if current.state in LIVE_ORDER_STATES:
            raise InvalidStateTransition(current.state.value, OrderState.RECONCILED.value)
        return self._apply(
            order_intent_id,
            OrderState.RECONCILED,
            updates={"reconciliation_note": note},
        )

    def record_closed(self, order_intent_id: UUID, *, note: str | None = None) -> OrderRecord:
        updates: dict[str, object] = {}
        if note is not None:
            updates["reconciliation_note"] = note
        return self._apply(order_intent_id, OrderState.CLOSED, updates=updates)

    def record_reviewed(self, order_intent_id: UUID) -> OrderRecord:
        return self._apply(order_intent_id, OrderState.REVIEWED, updates={})

    # ── Internals ─────────────────────────────────────────────────────────
    def _record_fill(
        self,
        order_intent_id: UUID,
        *,
        event_id: str | None,
        sequence: int,
        filled_quantity: Decimal,
        average_fill_price: Decimal,
        venue_order_id: str | None,
        commission: Decimal,
        slippage: Decimal | None,
        venue_position_id: str | None,
    ) -> OrderRecord:
        if filled_quantity <= 0:
            raise ValueError("fill quantity must be positive")
        current = self._store.get_order(order_intent_id)
        if current is None:
            raise ValueError(f"unknown order_intent_id {order_intent_id}")
        if current.state in (OrderState.CANCELLED, OrderState.REJECTED):
            raise ExecutionDivergenceError(
                DiscrepancyCode.IDENTIFIER_MISMATCH,
                f"fill event for a {current.state.value} order",
                order_intent_id=order_intent_id,
            )
        if current.state in (OrderState.RECONCILED, OrderState.CLOSED, OrderState.REVIEWED):
            raise ExecutionDivergenceError(
                DiscrepancyCode.IDENTIFIER_MISMATCH,
                f"fill event for an already-{current.state.value} order",
                order_intent_id=order_intent_id,
            )
        if event_id is not None and event_id in current.processed_event_ids:
            return current  # duplicate venue event — already applied (never double-count)
        cumulative = current.filled_quantity + filled_quantity
        if cumulative > current.requested_quantity:
            raise ExecutionDivergenceError(
                DiscrepancyCode.OVERFILL,
                f"cumulative fill {cumulative} exceeds requested {current.requested_quantity}",
                order_intent_id=order_intent_id,
            )
        if current.filled_quantity > 0:
            average = (
                (current.average_fill_price or Decimal("0")) * current.filled_quantity
                + average_fill_price * filled_quantity
            ) / cumulative
        else:
            average = average_fill_price
        target = (
            OrderState.FILLED
            if cumulative == current.requested_quantity
            else OrderState.PARTIALLY_FILLED
        )
        updates: dict[str, object] = {
            "filled_quantity": cumulative,
            "remaining_quantity": current.requested_quantity - cumulative,
            "average_fill_price": average,
            "commission": current.commission + commission,
            "last_event_sequence": max(current.last_event_sequence, sequence),
        }
        if venue_order_id is not None:
            updates["venue_order_id"] = venue_order_id
        if venue_position_id is not None:
            updates["venue_position_id"] = venue_position_id
        if slippage is not None:
            updates["slippage"] = slippage
        return self._apply(order_intent_id, target, event_id=event_id, updates=updates)

    def _apply(
        self,
        order_intent_id: UUID,
        target: OrderState,
        *,
        event_id: str | None = None,
        updates: dict[str, object] | None = None,
    ) -> OrderRecord:
        when = self._clock.now()
        field_updates = dict(updates or {})
        for _attempt in range(4):
            current = self._store.get_order(order_intent_id)
            if current is None:
                raise ValueError(f"unknown order_intent_id {order_intent_id}")
            if event_id is not None and event_id in current.processed_event_ids:
                return current  # duplicate venue event — already applied
            if not is_valid_order_transition(current.state, target):
                if (
                    target in (OrderState.PARTIALLY_FILLED, OrderState.FILLED)
                    and current.state is OrderState.SUBMITTED
                ):
                    # Fill before ACK: synthesize the missing ACK atomically.
                    acked = self._transition(
                        current,
                        OrderState.ACKNOWLEDGED,
                        when,
                        {"venue_order_id": field_updates.get("venue_order_id")}
                        if field_updates.get("venue_order_id") is not None
                        else {},
                    )
                    try:
                        current = self._store.update_order(acked, current.version)
                    except StaleStateError:
                        continue
                    continue  # re-evaluate from ACKNOWLEDGED
                raise InvalidStateTransition(current.state.value, target.value)
            next_record = self._transition(current, target, when, field_updates)
            if event_id is not None:
                next_record = self._stamp_event(next_record, event_id)
            try:
                return self._store.update_order(next_record, current.version)
            except StaleStateError:
                continue
        raise StaleStateError(order_intent_id, -1, -1)

    def _transition(
        self,
        current: OrderRecord,
        target: OrderState,
        when: datetime,
        field_updates: dict[str, object],
    ) -> OrderRecord:
        assert_valid_order_transition(current.state, target)
        updates: dict[str, object] = {
            "state": target,
            "updated_at": when,
            "version": current.version + 1,
        }
        updates.update(field_updates)
        timestamp_fields = {
            OrderState.SUBMITTED: "submitted_at",
            OrderState.ACKNOWLEDGED: "acknowledged_at",
            OrderState.FILLED: "filled_at",
            OrderState.CANCELLED: "cancelled_at",
            OrderState.REJECTED: "rejected_at",
            OrderState.RECONCILED: "reconciled_at",
            OrderState.CLOSED: "closed_at",
            OrderState.REVIEWED: "reviewed_at",
        }
        if target in timestamp_fields:
            updates.setdefault(timestamp_fields[target], when)
        return current.model_copy(update=updates)

    def _stamp_event(self, record: OrderRecord, event_id: str) -> OrderRecord:
        processed = (*record.processed_event_ids, event_id)
        return record.model_copy(update={"processed_event_ids": processed[-self._max_processed :]})

    def _update_fields(
        self, order_intent_id: UUID, field_updates: dict[str, object]
    ) -> OrderRecord:
        """CAS update of fields without a state transition (healing bookkeeping)."""
        for _attempt in range(4):
            current = self._store.get_order(order_intent_id)
            if current is None:
                raise ValueError(f"unknown order_intent_id {order_intent_id}")
            next_record = current.model_copy(
                update={
                    **field_updates,
                    "updated_at": self._clock.now(),
                    "version": current.version + 1,
                }
            )
            try:
                return self._store.update_order(next_record, current.version)
            except StaleStateError:
                continue
        raise StaleStateError(order_intent_id, -1, -1)
