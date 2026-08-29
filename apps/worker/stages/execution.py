"""Paper execution stage: OrderIntent → Nautilus paper venue (Phase 7).

INV-6 discipline applies even in PAPER mode:

1. the order is persisted as SUBMITTED *before* the venue call;
2. each venue ``ExecutionReport`` is applied through the execution applier
   (duplicate-safe, machine-checked) and emitted as a canonical event;
3. a FILLED report updates the paper ledger (position persistence + possible
   ``TradeOutcome``) and advances the trade lifecycle;
4. **no real broker execution is allowed**: the stage refuses to run unless
   ``operating_mode`` is exactly PAPER.

Redelivery safety: if the order record has already left ORDER_INTENT, the
venue is never called again.
"""

from __future__ import annotations

import time

from core.domain.enums import (
    ExecutionState,
    OrderState,
    PipelineStageName,
    TradeLifecycleState,
)
from core.schemas import ExecutionReport, OrderIntent
from core.schemas.events import DomainEvent

from apps.worker.lifecycle import transition
from apps.worker.stages.base import Stage, StageRuntime

__all__ = ["PaperExecutionStage"]

_PRODUCER = "apps.worker.execution"


class PaperExecutionStage(Stage):
    name = PipelineStageName.EXECUTION
    consumes = ("order.intent.created",)
    producer = _PRODUCER

    def process(self, rt: StageRuntime, event: DomainEvent) -> list[DomainEvent]:
        intent = OrderIntent.model_validate(event.payload)
        trace_id = event.trace_id
        assert trace_id is not None

        # Hard boundary: PAPER only. Live modes are refused outright.
        if rt.config.operating_mode.value != "PAPER":
            raise RuntimeError(
                f"execution stage refuses mode {rt.config.operating_mode.value}: "
                "no real broker execution is allowed in this milestone"
            )

        record = rt.execution_store.get_order(intent.order_intent_id)
        if record is not None and record.state is not OrderState.ORDER_INTENT:
            return []  # already executed (redelivery after crash)

        applier = rt.extras["applier"]
        applier.record_submitted(intent.order_intent_id)  # write before send (INV-6)

        snapshot = rt.last_snapshot(intent.instrument_id)
        if snapshot is None:
            raise ValueError(f"no snapshot for {intent.instrument_id} at execution time")

        executors = rt.extras["paper_executor"]
        executor = executors.get(intent.instrument_id)
        if executor is None:
            raise ValueError(f"no paper executor for {intent.instrument_id}")
        began = time.perf_counter()
        reports: list[ExecutionReport] = executor.submit(intent, snapshot)
        events: list[DomainEvent] = []

        filled: ExecutionReport | None = None
        rejected = False
        for report in reports:
            if report.status is ExecutionState.SUBMITTED:
                events.append(self.make_event(rt, "order.submitted", report, trace_id=trace_id))
            elif report.status is ExecutionState.ACKNOWLEDGED:
                applier.record_acknowledged(
                    intent.order_intent_id,
                    venue_order_id=report.venue_order_id,
                    event_id=str(report.execution_report_id),
                )
                events.append(self.make_event(rt, "order.acknowledged", report, trace_id=trace_id))
            elif report.status in (ExecutionState.FILLED, ExecutionState.PARTIAL_FILL):
                if report.average_fill_price is None:
                    raise ValueError("fill report requires average_fill_price")
                applier.record_fill(
                    intent.order_intent_id,
                    event_id=str(report.execution_report_id),
                    sequence=report.sequence,
                    filled_quantity=report.filled_quantity,
                    average_fill_price=report.average_fill_price,
                    venue_order_id=report.venue_order_id,
                    commission=report.commission,
                    slippage=report.slippage,
                )
                events.append(self.make_event(rt, "order.filled", report, trace_id=trace_id))
                filled = report
            elif report.status is ExecutionState.REJECTED:
                applier.record_rejected(
                    intent.order_intent_id,
                    reason=report.reject_reason or "paper venue reject",
                    event_id=str(report.execution_report_id),
                )
                events.append(self.make_event(rt, "order.rejected", report, trace_id=trace_id))
                rejected = True

        if rejected:
            rt.operational_metrics.observe_execution("rejected", time.perf_counter() - began)
            transition(
                rt,
                trace_id,
                TradeLifecycleState.ORDER_REJECTED,
                fields={"error": "paper venue rejected the order"},
            )
            return events
        if filled is None:
            raise RuntimeError(
                f"paper venue returned no terminal report for {intent.order_intent_id}"
            )
        rt.operational_metrics.observe_execution("filled", time.perf_counter() - began)

        after_fill = rt.execution_store.get_order(intent.order_intent_id)
        if after_fill is not None and after_fill.state is OrderState.FILLED:
            applier.record_closed(intent.order_intent_id, note="paper fill applied")
        application = rt.ledger.apply_fill(filled, intent, trace_id=trace_id)
        if application.outcome is None and application.position is not None:
            opened = rt.ledger.position(intent.instrument_id)
            if opened is not None and (
                intent.stop_loss is not None or intent.take_profit is not None
            ):
                opened.stop_loss = intent.stop_loss
                opened.take_profit = intent.take_profit
        if application.outcome is not None:
            # The outcome is emitted before the position update: the accounting
            # stage is idempotent per (trace, stage) and a closing fill carries
            # both events — the outcome application must win that race.
            events.append(
                self.make_event(rt, "trade.closed", application.outcome, trace_id=trace_id)
            )
            transition(
                rt,
                trace_id,
                TradeLifecycleState.POSITION_CLOSED,
                fields={"trade_id": application.outcome.trade_id},
            )
        if application.position is not None:
            events.append(
                self.make_event(rt, "position.updated", application.position, trace_id=trace_id)
            )
        if application.outcome is None and application.position is not None:
            transition(
                rt,
                trace_id,
                TradeLifecycleState.POSITION_OPEN,
                fields={"position_id": application.position.position_id},
            )
        return events
