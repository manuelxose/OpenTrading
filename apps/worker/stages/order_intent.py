"""Order-intent stage: risk-approved decision → canonical OrderIntent (INV-2).

The ``order_intent_id`` is content-derived (UUIDv5 over the decision id), so a
redelivered risk event yields the identical idempotency key. The full order
lifecycle is persisted through the execution applier:

    CANDIDATE → APPROVED → ORDER_INTENT   (this stage)
    SUBMITTED → ACKNOWLEDGED → FILLED/REJECTED → CLOSED → REVIEWED   (execution)

A redelivery after a crash finds the order already at ORDER_INTENT (or later)
and is a no-op — the paper venue never sees the same order twice.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid5

from core.domain.enums import (
    OrderSide,
    OrderType,
    PipelineStageName,
    RiskDecisionType,
    SignalDirection,
    TradeLifecycleState,
)
from core.schemas import OrderIntent, RiskDecision
from core.schemas.base import Provenance
from core.schemas.events import DomainEvent

from apps.worker.lifecycle import transition
from apps.worker.stages.base import Stage, StageRuntime

__all__ = ["OrderIntentStage"]

_PRODUCER = "apps.worker.order-intent"

_INTENT_NS = UUID("9c2e4f6a-7b8d-4c1e-9f0a-2b3c4d5e6f7a")


class OrderIntentStage(Stage):
    name = PipelineStageName.ORDER_INTENT
    consumes = ("risk.approved", "risk.resized")
    producer = _PRODUCER

    def process(self, rt: StageRuntime, event: DomainEvent) -> list[DomainEvent]:
        decision = RiskDecision.model_validate(event.payload)
        trace_id = event.trace_id
        assert trace_id is not None
        if decision.decision is RiskDecisionType.REJECT:
            return []
        now = rt.clock.now()

        order_intent_id = uuid5(_INTENT_NS, str(decision.decision_id))
        existing = rt.execution_store.get_order(order_intent_id)
        if existing is not None:
            return []  # already recorded (redelivery after crash)

        lifecycle = rt.store.get_lifecycle_by_trace(trace_id)
        if lifecycle is None:
            raise ValueError(f"no lifecycle for trace {trace_id}")
        strategy_id = lifecycle.strategy_id
        strategy_version = lifecycle.strategy_version
        instrument_id = lifecycle.instrument_id
        direction = lifecycle.direction
        if direction is None:
            raise ValueError(f"lifecycle {lifecycle.lifecycle_id} has no direction")

        if decision.approved_quantity is None or decision.approved_stop is None:
            raise ValueError("approved risk decision requires approved quantity and stop")

        side = OrderSide.BUY if direction is SignalDirection.LONG else OrderSide.SELL
        instrument = rt.instruments[instrument_id]
        units = decision.approved_quantity * instrument.contract_size
        position = rt.ledger.position(instrument_id)
        if position is not None and position.side.value != direction.value:
            # Exit order: never size the close beyond the open position.
            units = min(units, position.quantity)
            if units <= 0:
                raise ValueError("close order cannot be sized below one unit")
        intent = OrderIntent(
            order_intent_id=order_intent_id,
            risk_decision_id=decision.decision_id,
            proposal_id=decision.proposal_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            instrument_id=instrument_id,
            operating_mode=rt.config.operating_mode,
            side=side,
            order_type=OrderType.MARKET,
            quantity=units,
            stop_loss=decision.approved_stop,
            take_profit=lifecycle.take_profit,
            max_slippage=rt.policy.max_slippage_relative,
            valid_until=now + timedelta(seconds=rt.config.cycle_interval_seconds),
            created_by=_PRODUCER,
            trace_id=trace_id,
            produced_at=now,
            provenance=Provenance(producer=_PRODUCER, produced_at=now),
        )

        applier = rt.extras["applier"]
        applier.record_candidate(
            order_intent_id=order_intent_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            instrument_id=instrument_id,
            side=side,
            order_type=OrderType.MARKET,
            requested_quantity=intent.quantity,
        )
        applier.record_approved(order_intent_id)
        applier.record_order_intent(intent, venue="PAPER")
        rt.store.save_context_fragment(
            trace_id,
            "order_intent",
            intent.model_dump(mode="json"),
            instrument_id=instrument_id,
            updated_at=now,
        )

        transition(
            rt,
            trace_id,
            TradeLifecycleState.ORDER_CREATED,
            fields={"order_intent_id": order_intent_id},
        )
        rt.audit.record(
            "order.intent.created",
            target=str(order_intent_id),
            trace_id=trace_id,
            metadata={"side": side.value, "quantity": str(intent.quantity)},
        )
        return [self.make_event(rt, "order.intent.created", intent, trace_id=trace_id)]
