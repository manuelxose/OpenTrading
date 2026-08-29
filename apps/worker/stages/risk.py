"""Risk stage: TradeProposal → deterministic RiskDecision (Phase 7, INV-4).

The Risk Engine is a pure function over (proposal, account, portfolio,
snapshot, strategy, policy, instrument):

- account state comes from the persisted ``PaperAccountRecord`` (only
  deterministic execution outcomes update it);
- portfolio state comes from the ledger's open positions with current marks;
- close proposals (opposite direction, size ≤ open position) are evaluated
  against the portfolio *after* the exit, so closing never trips
  ``MAX_POSITIONS_REACHED``.

Emits ``risk.approved`` / ``risk.resized`` / ``risk.rejected`` and advances the
trace lifecycle.
"""

from __future__ import annotations

from typing import Any

from core.domain.enums import (
    PipelineStageName,
    RiskDecisionType,
    TradeLifecycleState,
)
from core.schemas import RiskDecision, TradeProposal
from core.schemas.events import DomainEvent
from engines.risk.engine import evaluate_proposal

from apps.worker.config import strategy_configuration
from apps.worker.lifecycle import transition
from apps.worker.stages.base import Stage, StageRuntime

__all__ = ["RiskStage"]

_PRODUCER = "apps.worker.risk"


class RiskStage(Stage):
    name = PipelineStageName.RISK
    consumes = ("trade.proposal.created",)
    producer = _PRODUCER

    def process(self, rt: StageRuntime, event: DomainEvent) -> list[DomainEvent]:
        proposal = TradeProposal.model_validate(event.payload)
        trace_id = event.trace_id
        assert trace_id is not None
        now = rt.clock.now()
        config = rt.config

        account = rt.store.get_account(config.account_id)
        if account is None:
            raise ValueError(f"paper account {config.account_id!r} not initialized")
        ledger = rt.ledger
        snapshot = rt.last_snapshot(proposal.instrument_id)
        marks = ledger.marks({proposal.instrument_id: snapshot}) if snapshot is not None else {}
        eval_now = snapshot.as_of if snapshot is not None else now

        pending_orders = self._pending_orders(rt)
        portfolio = ledger.portfolio_state(account, marks, pending_orders, eval_now)
        if self._is_close(ledger, proposal):
            # Exit proposal: evaluate against the post-exit portfolio.
            portfolio = self._post_exit_portfolio(rt, ledger, portfolio, proposal)

        decision: RiskDecision = evaluate_proposal(
            proposal=proposal,
            account=ledger.account_state(account, eval_now),
            portfolio=portfolio,
            snapshot=snapshot,
            strategy=strategy_configuration(config, eval_now),
            policy=rt.policy,
            instrument=rt.instruments[proposal.instrument_id],
        )
        rt.store.save_context_fragment(
            trace_id,
            "risk_decision",
            decision.canonical_dict(),
            instrument_id=proposal.instrument_id,
            updated_at=now,
        )

        event_name = {
            RiskDecisionType.APPROVE: "risk.approved",
            RiskDecisionType.RESIZE: "risk.resized",
            RiskDecisionType.REJECT: "risk.rejected",
        }[decision.decision]
        lifecycle_target = (
            TradeLifecycleState.RISK_REJECTED
            if decision.decision is RiskDecisionType.REJECT
            else TradeLifecycleState.RISK_APPROVED
        )
        transition(
            rt,
            trace_id,
            lifecycle_target,
            fields={
                "risk_decision_id": decision.decision_id,
                "error": (
                    "; ".join(code.value for code in decision.reason_codes)
                    if decision.decision is RiskDecisionType.REJECT
                    else None
                ),
            },
        )
        rt.audit.record(
            f"risk.{decision.decision.value.lower()}",
            target=str(decision.proposal_id),
            trace_id=trace_id,
            metadata={
                "approved_quantity": str(decision.approved_quantity or ""),
                "reason_codes": [code.value for code in decision.reason_codes],
            },
        )
        return [self.make_event(rt, event_name, decision, trace_id=trace_id)]

    @staticmethod
    def _is_close(ledger: Any, proposal: TradeProposal) -> bool:
        position = ledger.position(proposal.instrument_id)
        if position is None:
            return False
        position_direction: str = str(position.side.value)
        return proposal.direction.value != position_direction

    @staticmethod
    def _post_exit_portfolio(
        rt: StageRuntime, ledger: object, portfolio: object, proposal: TradeProposal
    ) -> object:
        """Portfolio view after the proposed exit: the closing instrument is
        excluded from positions and exposure so closing never trips
        MAX_POSITIONS_REACHED / exposure limits."""
        from decimal import Decimal as D

        from core.schemas.risk import PortfolioExposure, PortfolioState

        remaining = [
            p
            for p in portfolio.positions  # type: ignore[attr-defined]
            if p.instrument_id != proposal.instrument_id
        ]
        by_instrument: dict[str, D] = {}
        net_by_currency: dict[str, D] = {}
        total = D("0")
        for position in remaining:
            mark = position.mark_price or position.average_entry_price
            notional = position.quantity * mark  # units x price (quote ccy)
            total += notional
            by_instrument[position.instrument_id] = notional
            instrument = rt.instruments[position.instrument_id]
            quote = str(getattr(instrument, "quote_currency", ""))
            sign = D("1") if position.side.value == "LONG" else D("-1")
            net_by_currency[quote] = net_by_currency.get(quote, D("0")) + sign * notional
        return PortfolioState(
            account_id=portfolio.account_id,  # type: ignore[attr-defined]
            positions=remaining,
            pending_order_count=portfolio.pending_order_count,  # type: ignore[attr-defined]
            exposure=PortfolioExposure(
                total_notional=total,
                by_instrument=by_instrument,
                by_asset_class={},
                net_by_currency=net_by_currency,
            ),
            as_of=portfolio.as_of,  # type: ignore[attr-defined]
            produced_at=portfolio.produced_at,  # type: ignore[attr-defined]
            provenance=portfolio.provenance,  # type: ignore[attr-defined]
        )

    @staticmethod
    def _pending_orders(rt: StageRuntime) -> int:
        from core.schemas.execution import LIVE_ORDER_STATES

        orders = rt.execution_store.list_orders()
        return sum(1 for order in orders if order.state in LIVE_ORDER_STATES)
