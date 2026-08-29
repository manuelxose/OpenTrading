"""Position-management stage: SL/TP monitoring and close proposals (Phase 7).

Consumes every new ``market.snapshot.created`` and:

- refreshes the runtime's latest snapshot per instrument;
- for each open position whose stop-loss or take-profit level is crossed,
  emits a *close* ``TradeProposal`` (opposite direction, full size) through
  the regular proposal → risk → order-intent → execution chain — exits use the
  exact same canonical path as entries (INV-2);
- skips instruments that already have a live close order in flight
  (double-close protection).

Stop/take levels travel on the lifecycle (``stop_loss``/``take_profit``), so
they survive worker restarts and are reattached to ledger positions on load.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from core.domain.enums import (
    OrderState,
    OrderType,
    PipelineStageName,
    PositionSide,
    SignalDirection,
    TradeLifecycleState,
)
from core.schemas import MarketSnapshot, TradeProposal
from core.schemas.base import Provenance
from core.schemas.events import DomainEvent
from core.schemas.execution import LIVE_ORDER_STATES
from core.schemas.pipeline import TradeLifecycle

from apps.worker.stages.base import Stage, StageRuntime

__all__ = ["PositionsStage"]

_PRODUCER = "apps.worker.positions"

#: Order states that mean a close is already heading to the venue: anything
#: before a terminal state (FILLED / CANCELLED / REJECTED / RECONCILED /
#: CLOSED / REVIEWED / RISK_REJECTED).
IN_FLIGHT_ORDER_STATES: frozenset[OrderState] = LIVE_ORDER_STATES | frozenset(
    {OrderState.CANDIDATE, OrderState.APPROVED, OrderState.ORDER_INTENT}
)

#: Lifecycle states of a close chain already in motion (created by this stage
#: and advanced by proposal/risk/order-intent), covering the window before any
#: execution-store record exists.
CLOSE_CHAIN_LIFECYCLE_STATES: frozenset[TradeLifecycleState] = frozenset(
    {
        TradeLifecycleState.PROPOSED,
        TradeLifecycleState.RISK_APPROVED,
        TradeLifecycleState.ORDER_CREATED,
    }
)


class PositionsStage(Stage):
    name = PipelineStageName.POSITIONS
    consumes = ("market.snapshot.created",)
    producer = _PRODUCER

    def process(self, rt: StageRuntime, event: DomainEvent) -> list[DomainEvent]:
        snapshot = MarketSnapshot.model_validate(event.payload)
        instrument_id = snapshot.instrument_id
        rt.latest_snapshots[instrument_id] = snapshot
        self._reattach_stop_levels(rt)

        events: list[DomainEvent] = []
        position = rt.ledger.position(instrument_id)
        if position is None:
            return events
        rt.ledger.record_mark(snapshot)
        if self._close_in_flight(rt, instrument_id):
            return events

        mark = snapshot.mid
        stop = position.stop_loss
        take = position.take_profit
        crossed = False
        if position.side is PositionSide.LONG:
            if stop is not None and mark <= stop:
                crossed = True
            if take is not None and mark >= take:
                crossed = True
        else:
            if stop is not None and mark >= stop:
                crossed = True
            if take is not None and mark <= take:
                crossed = True
        if not crossed:
            return events

        now = rt.clock.now()
        trace_id = uuid4()
        entry_lifecycle = next(
            (
                lifecycle
                for lifecycle in rt.store.list_lifecycles()
                if lifecycle.instrument_id == instrument_id
                and lifecycle.state is TradeLifecycleState.POSITION_OPEN
            ),
            None,
        )
        trade_trace_id = entry_lifecycle.trace_id if entry_lifecycle is not None else trace_id
        rt.store.save_context_fragment(
            trace_id,
            "telemetry",
            {"trade_trace_id": str(trade_trace_id)},
            instrument_id=instrument_id,
            updated_at=now,
        )
        close_direction = (
            SignalDirection.SHORT if position.side is PositionSide.LONG else SignalDirection.LONG
        )
        level_kind = (
            "stop" if stop is not None and self._crossed_stop(position, mark, stop) else "take"
        )
        tick = rt.instruments[instrument_id].tick_size
        contract_size = rt.instruments[instrument_id].contract_size
        # Close orders still carry a stop for the Risk Engine's sizing path:
        # one tick beyond the mark (the exit decision itself is the risk gate).
        close_stop = mark + tick if position.side is PositionSide.LONG else mark - tick
        proposal = TradeProposal(
            proposal_id=uuid4(),
            strategy_id=rt.config.strategy_id,
            strategy_version=rt.config.strategy_version,
            instrument_id=instrument_id,
            operating_mode=rt.config.operating_mode,
            direction=close_direction,
            order_type=OrderType.MARKET,
            quantity=position.quantity / contract_size,  # lots (advisory)
            stop_loss=close_stop,
            source_signal_ids=[],
            rationale=f"SL/TP exit: mark {mark} crossed {level_kind} level",
            expires_at=now + timedelta(seconds=rt.config.cycle_interval_seconds),
            trace_id=trace_id,
            produced_at=now,
            provenance=Provenance(producer=_PRODUCER, produced_at=now),
        )
        rt.store.save_lifecycle(
            TradeLifecycle(
                lifecycle_id=uuid4(),
                trace_id=trace_id,
                proposal_id=proposal.proposal_id,
                strategy_id=rt.config.strategy_id,
                strategy_version=rt.config.strategy_version,
                instrument_id=instrument_id,
                state=TradeLifecycleState.PROPOSED,
                direction=close_direction,
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
        rt.audit.record(
            "position.close.triggered",
            target=position.venue_position_id or f"paper:{instrument_id}",
            trace_id=trace_id,
            metadata={"mark": str(mark), "quantity": str(position.quantity)},
        )
        events.append(self.make_event(rt, "trade.proposal.created", proposal, trace_id=trace_id))
        return events

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _crossed_stop(position: object, mark: Decimal, stop: Decimal) -> bool:
        if position.side is PositionSide.LONG:  # type: ignore[attr-defined]
            return mark <= stop
        return mark >= stop

    @staticmethod
    def _close_in_flight(rt: StageRuntime, instrument_id: str) -> bool:
        orders = rt.execution_store.list_orders()
        for order in orders:
            # Any non-terminal order for this instrument — including CANDIDATE /
            # APPROVED / ORDER_INTENT, which precede SUBMITTED — blocks a second
            # close proposal (a later snapshot must not re-trigger the exit
            # while the first close chain is still working its way to the venue).
            if order.instrument_id == instrument_id and order.state in IN_FLIGHT_ORDER_STATES:
                return True
        # Guard the window before the order-intent stage persists anything: a
        # close chain already proposed (PROPOSED → RISK_APPROVED → ORDER_CREATED)
        # for this instrument also blocks re-proposal.
        for lifecycle in rt.store.list_lifecycles():
            if lifecycle.instrument_id != instrument_id:
                continue
            if lifecycle.state in CLOSE_CHAIN_LIFECYCLE_STATES:
                return True
        return False

    @staticmethod
    def _reattach_stop_levels(rt: StageRuntime) -> None:
        """Reattach persisted SL/TP levels to ledger positions (restart)."""
        for lifecycle in rt.store.list_lifecycles():
            if lifecycle.state is not TradeLifecycleState.POSITION_OPEN:
                continue
            if lifecycle.position_id is None:
                continue
            position = rt.ledger.position(lifecycle.instrument_id)
            if position is None:
                continue
            if position.stop_loss is None:
                position.stop_loss = lifecycle.stop_loss
            if position.take_profit is None:
                position.take_profit = lifecycle.take_profit
