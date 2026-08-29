"""Mappings between canonical Core contracts and MT4 wire messages.

``OrderIntent`` is the only canonical crossing object (INV-2); the bridge is the
last mile where it becomes a wire command. Venue events map back into canonical
``ExecutionReport`` so the Core never handles ``MT4Order`` anywhere else.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from core.domain.enums import ExecutionState
from core.schemas.base import Provenance
from core.schemas.trading import ExecutionReport, OrderIntent

from adapters.mt4.protocol import (
    FillEvent,
    PartialFillEvent,
    SubmitOrderCommand,
    WireMessage,
)

__all__ = [
    "execution_report_from_fill",
    "submit_command_from_intent",
]


def submit_command_from_intent(
    intent: OrderIntent,
    *,
    now: datetime,
    sequence: int,
    trace_id: UUID | None = None,
    expires_at: datetime | None = None,
    message_id: UUID | None = None,
) -> SubmitOrderCommand:
    """Translate the canonical OrderIntent into a wire submit_order command.

    ``order_intent_id`` is the idempotency key for every venue (INV-2).
    """
    return SubmitOrderCommand(
        message_id=message_id or uuid4(),
        trace_id=trace_id or intent.trace_id,
        timestamp=now,
        sequence=sequence,
        order_intent_id=intent.order_intent_id,
        strategy_id=intent.strategy_id,
        strategy_version=intent.strategy_version,
        expires_at=expires_at or intent.valid_until,
        symbol=intent.instrument_id,
        side=intent.side,
        quantity=intent.quantity,
        order_type=intent.order_type,
        price=intent.price,
        stop_loss=intent.stop_loss,
        take_profit=intent.take_profit,
        max_slippage=intent.max_slippage,
        time_in_force=intent.time_in_force,
    )


def execution_report_from_fill(
    event: WireMessage,
    *,
    venue: str,
    now: datetime,
) -> ExecutionReport:
    """Map a venue fill event into the canonical ExecutionReport (INV-6)."""
    if isinstance(event, PartialFillEvent):
        return ExecutionReport(
            trace_id=event.trace_id,
            produced_at=now,
            provenance=Provenance(
                producer="mt4-adapter",
                produced_at=now,
                source_ids={"order_intent_id": str(event.order_intent_id)},
            ),
            execution_report_id=uuid4(),
            order_intent_id=event.order_intent_id,
            venue=venue,
            venue_order_id=event.venue_order_id,
            status=ExecutionState.PARTIAL_FILL,
            filled_quantity=event.filled_quantity,
            average_fill_price=event.average_fill_price,
            commission=event.commission,
            slippage=event.slippage,
            report_time=now,
            sequence=event.sequence,
            checksum=event.checksum,
        )
    if isinstance(event, FillEvent):
        return ExecutionReport(
            trace_id=event.trace_id,
            produced_at=now,
            provenance=Provenance(
                producer="mt4-adapter",
                produced_at=now,
                source_ids={"order_intent_id": str(event.order_intent_id)},
            ),
            execution_report_id=uuid4(),
            order_intent_id=event.order_intent_id,
            venue=venue,
            venue_order_id=event.venue_order_id,
            status=ExecutionState.FILLED,
            filled_quantity=event.filled_quantity,
            average_fill_price=event.average_fill_price,
            commission=event.commission,
            slippage=event.slippage,
            report_time=now,
            sequence=event.sequence,
            checksum=event.checksum,
        )
    raise TypeError(f"expected a fill event, got {type(event).__name__}")
