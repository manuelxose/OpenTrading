"""Proposal stage: fused signal → TradeProposal (Phase 7).

Deterministic proposal shaping — the LLM never sizes (INV-1):

- quantity is an *advisory* equity fraction of the paper account, floored to
  the instrument's lot step; the Risk Engine computes the final approved size;
- stop/take levels derive from the bar range (ATR ratio) around the mid;
- ``proposal_id`` is content-derived (UUIDv5), so redeliveries are idempotent.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from uuid import UUID, uuid5

from core.domain.enums import OrderType, PipelineStageName, SignalDirection, TradeLifecycleState
from core.schemas import MarketSnapshot, TradeProposal
from core.schemas.base import Provenance
from core.schemas.events import DomainEvent
from core.schemas.signals import FusedSignal

from apps.worker.lifecycle import transition
from apps.worker.stages.base import Stage, StageRuntime

__all__ = ["ProposalStage"]

_PRODUCER = "apps.worker.proposal"

_PROPOSAL_NS = UUID("5b8e7f6a-1d2c-4b3e-9a0f-8e7d6c5b4a3f")


class ProposalStage(Stage):
    name = PipelineStageName.PROPOSAL
    consumes = ("signal.fused",)
    producer = _PRODUCER

    def process(self, rt: StageRuntime, event: DomainEvent) -> list[DomainEvent]:
        signal = FusedSignal.model_validate(event.payload)
        trace_id = event.trace_id
        assert trace_id is not None
        if signal.direction is SignalDirection.FLAT:
            return []
        now = rt.clock.now()
        snapshot: MarketSnapshot | None = rt.last_snapshot(signal.instrument_id)
        mid = snapshot.mid if snapshot is not None else Decimal("0")

        proposal = self._build(rt, signal, snapshot, now)
        lifecycle = rt.store.get_lifecycle_by_trace(trace_id)
        stop = proposal.stop_loss
        take = proposal.take_profit
        rt.store.save_context_fragment(
            trace_id,
            "proposal",
            proposal.canonical_dict(),
            instrument_id=signal.instrument_id,
            updated_at=now,
        )
        transition(
            rt,
            trace_id,
            TradeLifecycleState.PROPOSED,
            fields={
                "proposal_id": proposal.proposal_id,
                "direction": proposal.direction,
                "stop_loss": stop,
                "take_profit": take,
            },
        )
        if lifecycle is not None:
            rt.audit.record(
                "trade.proposal.created",
                target=str(proposal.proposal_id),
                trace_id=trace_id,
                metadata={
                    "instrument": proposal.instrument_id,
                    "direction": proposal.direction.value,
                    "quantity": str(proposal.quantity),
                    "strength": signal.fused_strength,
                    "mid": str(mid),
                },
            )
        return [self.make_event(rt, "trade.proposal.created", proposal, trace_id=trace_id)]

    def _build(
        self,
        rt: StageRuntime,
        signal: FusedSignal,
        snapshot: MarketSnapshot | None,
        now: datetime,
    ) -> TradeProposal:
        config = rt.config
        instrument = rt.instruments[signal.instrument_id]
        if snapshot is None:
            raise ValueError(f"no market snapshot available for {signal.instrument_id}")
        mid = snapshot.mid
        account = rt.store.get_account(config.account_id)
        equity = account.equity if account is not None else config.starting_balance

        contract_size = Decimal(str(getattr(instrument, "contract_size", 1)))
        lot_size = instrument.lot_size
        step = instrument.lot_step
        min_lot = instrument.min_lot
        max_lot = instrument.max_lot
        notional_per_lot = contract_size * lot_size * mid
        if notional_per_lot <= 0:
            raise ValueError("instrument notional per lot must be positive")
        raw = equity * config.proposal.position_equity_pct / notional_per_lot
        quantity = self._floor_lot(raw, step, min_lot, max_lot)

        high = snapshot.high if snapshot.high is not None else mid
        low = snapshot.low if snapshot.low is not None else mid
        bar_range = high - low
        if bar_range <= 0:
            bar_range = mid * Decimal("0.0005")
        atr = bar_range
        stop = mid - atr * config.proposal.stop_atr_ratio
        take = mid + atr * config.proposal.take_atr_ratio
        if signal.direction is SignalDirection.SHORT:
            stop, take = (
                mid + atr * config.proposal.stop_atr_ratio,
                mid - atr * config.proposal.take_atr_ratio,
            )
        tick = instrument.tick_size
        stop = (stop / tick).to_integral_value(rounding=ROUND_DOWN) * tick
        take = (take / tick).to_integral_value(rounding=ROUND_DOWN) * tick

        proposal_id = uuid5(_PROPOSAL_NS, f"{signal.signal_id}:{config.strategy_id}")
        components = ", ".join(f"{c.name}={c.score:+.3f}" for c in signal.components)
        return TradeProposal(
            proposal_id=proposal_id,
            strategy_id=config.strategy_id,
            strategy_version=config.strategy_version,
            instrument_id=signal.instrument_id,
            operating_mode=config.operating_mode,
            direction=signal.direction,
            order_type=OrderType.MARKET,
            quantity=quantity,
            stop_loss=stop,
            take_profit=take,
            source_signal_ids=[str(signal.signal_id)],
            rationale=f"fused {signal.direction.value} strength={signal.fused_strength:.3f} "
            f"confidence={signal.confidence:.3f} inputs=[{components}]",
            expires_at=now + timedelta(seconds=config.cycle_interval_seconds * 2),
            trace_id=signal.trace_id,
            produced_at=now,
            provenance=Provenance(producer=_PRODUCER, produced_at=now),
        )

    @staticmethod
    def _floor_lot(value: Decimal, step: Decimal, min_lot: Decimal, max_lot: Decimal) -> Decimal:
        if step <= 0:
            raise ValueError("lot step must be positive")
        lots = (value / step).to_integral_value(rounding=ROUND_DOWN) * step
        lots = max(lots, min_lot)
        return min(lots, max_lot)
