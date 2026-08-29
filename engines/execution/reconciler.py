"""Broker reconciliation — the deterministic compare-and-heal pass (INV-6, §9).

Never assume ``send_order() == executed_trade``. Every restart loads persisted
state and compares it against live broker state across the five mandated axes:
open orders, positions, quantities, identifiers — and state consistency.

Resolution rules (documented in ADR-0021):

- **EXPLAINABLE** discrepancies are healed deterministically (inferred ACK,
  inferred fill from a broker position, position adoption, venue-side close).
- **WARNING** discrepancies are recorded; the broker is authority for *price*
  (exposure is unaffected), so its entry price is adopted.
- **MATERIAL** discrepancies (unknown broker order/position, missing
  acknowledged order, quantity/identifier mismatch, broker unreachable) are
  reported in the run and must flip the platform into SAFE_MODE — the
  reconciler itself never changes trading posture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from core.clock.clocks import Clock
from core.domain.enums import DiscrepancyCode, OrderSide, OrderState, PositionSide
from core.schemas.execution import (
    DEFAULT_PRICE_TOLERANCE,
    LIVE_ORDER_STATES,
    VENUE_TERMINAL_STATES,
    ExecutionPosition,
    OrderRecord,
    ReconciliationDiscrepancy,
    ReconciliationRun,
)

from engines.execution.applier import OrderStateApplier
from engines.execution.persistence import ExecutionStateStore

__all__ = ["BrokerReconciler", "BrokerView", "VenueViewPosition"]


@dataclass(frozen=True)
class VenueViewPosition:
    """Transport-agnostic view of one broker-side position."""

    venue_position_id: str
    magic: int
    account_id: str
    strategy_id: str | None
    instrument_id: str
    side: PositionSide
    quantity: Decimal
    average_entry_price: Decimal
    order_intent_id: UUID | None


@dataclass(frozen=True)
class BrokerView:
    """Transport-agnostic snapshot of live broker state for one reconciliation."""

    account: dict[str, object] | None
    positions: tuple[VenueViewPosition, ...]
    open_order_intent_ids: tuple[UUID, ...]
    broker_connected: bool = True
    trading_enabled: bool = True
    last_sequences: dict[str, int] = field(default_factory=dict)


def _discrepancy(
    code: DiscrepancyCode,
    severity: Literal["EXPLAINABLE", "WARNING", "MATERIAL"],
    explanation: str,
    *,
    order_intent_id: UUID | None = None,
    venue_position_id: str | None = None,
    venue_order_id: str | None = None,
    expected: str | None = None,
    observed: str | None = None,
    resolution: str | None = None,
) -> ReconciliationDiscrepancy:
    return ReconciliationDiscrepancy(
        code=code,
        severity=severity,
        order_intent_id=order_intent_id,
        venue_position_id=venue_position_id,
        venue_order_id=venue_order_id,
        expected=expected,
        observed=observed,
        explanation=explanation,
        resolution=resolution,
    )


def _expected_side(record: OrderRecord) -> PositionSide:
    return PositionSide.LONG if record.side is OrderSide.BUY else PositionSide.SHORT


class BrokerReconciler:
    """Compares persisted state with a :class:`BrokerView` and heals what is
    explainable. Material divergences are reported, never auto-reconciled."""

    def __init__(
        self,
        store: ExecutionStateStore,
        applier: OrderStateApplier,
        clock: Clock,
        *,
        price_tolerance: Decimal = DEFAULT_PRICE_TOLERANCE,
    ) -> None:
        self._store = store
        self._applier = applier
        self._clock = clock
        self._price_tolerance = price_tolerance

    def reconcile(self, view: BrokerView) -> ReconciliationRun:
        started_at = self._clock.now()
        discrepancies: list[ReconciliationDiscrepancy] = []
        resolved = 0
        adopted = 0
        positions_closed = 0

        if not view.broker_connected:
            # Broker data cannot be trusted: compare nothing, report, escalate.
            return ReconciliationRun(
                run_id=uuid4(),
                started_at=started_at,
                compared_at=self._clock.now(),
                broker_reachable=True,
                broker_connected=False,
                trading_enabled=view.trading_enabled,
                account=view.account,
                discrepancies=(
                    _discrepancy(
                        DiscrepancyCode.BROKER_UNREACHABLE,
                        "MATERIAL",
                        "broker reports disconnected — no authoritative venue state",
                    ),
                ),
                material_discrepancies=1,
                last_sequences=view.last_sequences,
            )

        db_orders = {o.order_intent_id: o for o in self._store.list_orders()}
        venue_open_ids = set(view.open_order_intent_ids)
        db_positions = {p.venue_position_id: p for p in self._store.list_positions(open_only=True)}

        def live_orders() -> list[OrderRecord]:
            # Fresh view: position adoption may already have filled orders.
            return [o for o in self._store.list_orders() if o.state in LIVE_ORDER_STATES]

        # ── 1. Venue-open orders we do not know (or disagree on) → MATERIAL ──
        for order_intent_id in sorted(venue_open_ids, key=str):
            record = db_orders.get(order_intent_id)
            if record is None:
                discrepancies.append(
                    _discrepancy(
                        DiscrepancyCode.UNEXPECTED_BROKER_ORDER,
                        "MATERIAL",
                        "broker reports an open order the platform never recorded",
                        order_intent_id=order_intent_id,
                    )
                )
            elif record.state is OrderState.FILLED:
                discrepancies.append(
                    _discrepancy(
                        DiscrepancyCode.IDENTIFIER_MISMATCH,
                        "MATERIAL",
                        "broker reports the order still open but the platform has it FILLED",
                        order_intent_id=order_intent_id,
                    )
                )
            elif record.state in (
                OrderState.SUBMITTED,
                OrderState.ACKNOWLEDGED,
                OrderState.PARTIALLY_FILLED,
            ):
                continue  # consistent live order (ACK healing happens in step 3)
            else:
                discrepancies.append(
                    _discrepancy(
                        DiscrepancyCode.UNEXPECTED_BROKER_ORDER,
                        "MATERIAL",
                        f"broker reports the order open but the platform has it "
                        f"{record.state.value}",
                        order_intent_id=order_intent_id,
                        observed=record.state.value,
                    )
                )

        # ── 2. Broker positions vs persisted positions (adoptions heal fills) ──
        venue_position_ids = {p.venue_position_id for p in view.positions}
        for position in view.positions:
            db_position = db_positions.get(position.venue_position_id)
            if db_position is not None:
                self._compare_known_position(position, db_position, discrepancies)
                continue

            # Unknown venue position id — attempt deterministic adoption.
            record = db_orders.get(position.order_intent_id) if position.order_intent_id else None
            if record is not None and record.state is OrderState.FILLED:
                if record.venue_position_id is None:
                    self._applier.adopt_position(
                        record.order_intent_id,
                        venue_position_id=position.venue_position_id,
                        note="position linked at reconciliation",
                    )
                if record.filled_quantity != position.quantity:
                    discrepancies.append(
                        _discrepancy(
                            DiscrepancyCode.QUANTITY_MISMATCH,
                            "MATERIAL",
                            "filled order quantity disagrees with the broker position",
                            order_intent_id=record.order_intent_id,
                            venue_position_id=position.venue_position_id,
                            expected=str(record.filled_quantity),
                            observed=str(position.quantity),
                        )
                    )
                else:
                    self._store.upsert_position(
                        self._to_execution_position(position, record.order_intent_id)
                    )
                    discrepancies.append(
                        _discrepancy(
                            DiscrepancyCode.POSITION_EVENT_LOST,
                            "EXPLAINABLE",
                            "broker position linked to a FILLED order whose "
                            "position event was lost",
                            order_intent_id=record.order_intent_id,
                            venue_position_id=position.venue_position_id,
                            resolution="position adopted",
                        )
                    )
                    adopted += 1
                continue

            # No provenance link: exactly one matching live order adopts it.
            candidates = [
                open_order
                for open_order in live_orders()
                if open_order.instrument_id == position.instrument_id
                and _expected_side(open_order) == position.side
                and open_order.requested_quantity - open_order.filled_quantity == position.quantity
            ]
            if len(candidates) == 1:
                target = candidates[0]
                self._applier.heal_fill(
                    target.order_intent_id,
                    venue_position_id=position.venue_position_id,
                    quantity=position.quantity,
                    average_fill_price=position.average_entry_price,
                    note="fill inferred from an unmatched broker position",
                )
                self._store.upsert_position(
                    self._to_execution_position(position, target.order_intent_id)
                )
                discrepancies.append(
                    _discrepancy(
                        DiscrepancyCode.FILL_EVENT_LOST,
                        "EXPLAINABLE",
                        "broker position matches exactly one open order — fill events were lost",
                        order_intent_id=target.order_intent_id,
                        venue_position_id=position.venue_position_id,
                        resolution="FILLED + position adopted",
                    )
                )
                resolved += 1
                adopted += 1
                continue

            discrepancies.append(
                _discrepancy(
                    DiscrepancyCode.UNEXPECTED_BROKER_POSITION,
                    "MATERIAL",
                    "broker position cannot be matched to any persisted order or position "
                    "(manual trade at the broker?)",
                    venue_position_id=position.venue_position_id,
                    observed=f"{position.instrument_id} {position.side.value} {position.quantity}",
                )
            )

        # ── 3. Our still-open orders vs the venue (after position adoption) ──
        for record in live_orders():
            if record.order_intent_id in venue_open_ids:
                if record.state is OrderState.SUBMITTED:
                    self._applier.heal_acknowledged(
                        record.order_intent_id,
                        note="ACK inferred from broker open orders at reconciliation",
                    )
                    discrepancies.append(
                        _discrepancy(
                            DiscrepancyCode.ORDER_ACK_LOST,
                            "EXPLAINABLE",
                            "broker holds the order open but the ACK was never recorded",
                            order_intent_id=record.order_intent_id,
                            resolution="ACKNOWLEDGED",
                        )
                    )
                    resolved += 1
                continue  # consistent live order

            # The venue is silent about an order we consider open.
            if record.state is OrderState.SUBMITTED:
                self._applier.record_cancelled(
                    record.order_intent_id,
                    note="no venue evidence at reconciliation (never acknowledged)",
                )
                self._applier.mark_reconciled(
                    record.order_intent_id,
                    note="closed at reconciliation: no venue evidence",
                )
                discrepancies.append(
                    _discrepancy(
                        DiscrepancyCode.ORDER_NEVER_ACKNOWLEDGED,
                        "EXPLAINABLE",
                        "submitted order left no trace at the broker — nothing executable",
                        order_intent_id=record.order_intent_id,
                        resolution="CANCELLED -> RECONCILED",
                    )
                )
                resolved += 1
                continue

            discrepancies.append(
                _discrepancy(
                    DiscrepancyCode.MISSING_BROKER_ORDER,
                    "MATERIAL",
                    f"broker lost an order the platform holds {record.state.value} "
                    "with no matching position",
                    order_intent_id=record.order_intent_id,
                )
            )

        # ── 4. Persisted open positions missing at the venue → closed there ──
        for venue_position_id, db_position in db_positions.items():
            if venue_position_id not in venue_position_ids:
                now = self._clock.now()
                self._store.upsert_position(
                    db_position.model_copy(update={"closed_at": now, "updated_at": now})
                )
                discrepancies.append(
                    _discrepancy(
                        DiscrepancyCode.POSITION_CLOSED_AT_VENUE,
                        "EXPLAINABLE",
                        "position no longer exists at the broker (manual close / TP / SL)",
                        venue_position_id=venue_position_id,
                        resolution="position closed",
                    )
                )
                positions_closed += 1

        # ── 5. Terminal orders consistent with the venue → RECONCILED ────────
        orders_reconciled = 0
        for record in db_orders.values():
            if record.state in VENUE_TERMINAL_STATES:
                material_for_order = any(
                    d.severity == "MATERIAL" and d.order_intent_id == record.order_intent_id
                    for d in discrepancies
                )
                if not material_for_order:
                    self._applier.mark_reconciled(
                        record.order_intent_id, note="consistent with broker at reconciliation"
                    )
                    orders_reconciled += 1

        run = ReconciliationRun(
            run_id=uuid4(),
            started_at=started_at,
            compared_at=self._clock.now(),
            broker_reachable=True,
            broker_connected=True,
            trading_enabled=view.trading_enabled,
            account=view.account,
            discrepancies=tuple(discrepancies),
            material_discrepancies=sum(1 for d in discrepancies if d.severity == "MATERIAL"),
            orders_reconciled=orders_reconciled,
            orders_resolved=resolved,
            positions_adopted=adopted,
            positions_closed=positions_closed,
            last_sequences=view.last_sequences,
        )
        # The service persists the run (with safe-mode transition flags) once
        # the controller has reacted; the reconciler never changes posture.
        return run

    # ── Helpers ───────────────────────────────────────────────────────────
    def _compare_known_position(
        self,
        position: VenueViewPosition,
        db_position: ExecutionPosition,
        discrepancies: list[ReconciliationDiscrepancy],
    ) -> None:
        if position.instrument_id != db_position.instrument_id or position.side != db_position.side:
            discrepancies.append(
                _discrepancy(
                    DiscrepancyCode.IDENTIFIER_MISMATCH,
                    "MATERIAL",
                    "broker position identity disagrees with the persisted position",
                    venue_position_id=position.venue_position_id,
                )
            )
            return
        if position.quantity != db_position.quantity:
            discrepancies.append(
                _discrepancy(
                    DiscrepancyCode.QUANTITY_MISMATCH,
                    "MATERIAL",
                    "broker position quantity disagrees with the persisted position",
                    venue_position_id=position.venue_position_id,
                    expected=str(db_position.quantity),
                    observed=str(position.quantity),
                )
            )
            return
        drift = abs(position.average_entry_price - db_position.average_entry_price)
        if drift > db_position.average_entry_price * self._price_tolerance:
            now = self._clock.now()
            self._store.upsert_position(
                db_position.model_copy(
                    update={
                        "average_entry_price": position.average_entry_price,
                        "updated_at": now,
                    }
                )
            )
            discrepancies.append(
                _discrepancy(
                    DiscrepancyCode.PRICE_DRIFT,
                    "WARNING",
                    "entry price drifted beyond tolerance — broker price is authority",
                    venue_position_id=position.venue_position_id,
                    expected=str(db_position.average_entry_price),
                    observed=str(position.average_entry_price),
                    resolution="broker price adopted",
                )
            )

    def _to_execution_position(
        self, position: VenueViewPosition, order_intent_id: UUID
    ) -> ExecutionPosition:
        now = self._clock.now()
        return ExecutionPosition(
            venue_position_id=position.venue_position_id,
            account_id=position.account_id,
            instrument_id=position.instrument_id,
            side=position.side,
            quantity=position.quantity,
            average_entry_price=position.average_entry_price,
            order_intent_id=order_intent_id,
            opened_at=now,
            updated_at=now,
        )
