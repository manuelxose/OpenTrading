"""Deterministic Risk & Policy Engine (architecture §7, INV-4, ADR-0015, ADR-0018).

100% own code. No LLM, no agent, no prompt, no probabilistic interpretation.

Pipeline::

    TradeProposal ──┐
    AccountState   ─┤
    PortfolioState ─┤
    MarketSnapshot ─┤ hard policy checks → REJECT (reason_codes)
    StrategyConfig ─┤
    RiskPolicy     ─┤
    Instrument     ─┘
        │ (no hard violation)
        ▼
    deterministic sizing → APPROVE | RESIZE | REJECT

The engine is a pure function of its inputs: no state, no IO, no wall clock.
The decision id and ``inputs_hash`` derive from the canonical inputs, so
identical inputs produce identical decisions.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid5

from core.domain.enums import RiskDecisionType, RiskReasonCode
from core.schemas.base import Provenance
from core.schemas.market import Instrument, MarketSnapshot
from core.schemas.risk import (
    AccountState,
    PortfolioState,
    RiskPolicy,
    StrategyConfiguration,
)
from core.schemas.trading import RiskDecision, TradeProposal

from engines.risk.checks import RiskEngineInputError, run_hard_checks
from engines.risk.sizing import compute_size_plan

__all__ = [
    "RISK_ENGINE_VERSION",
    "RiskEngine",
    "RiskEngineInputError",
    "compute_inputs_hash",
    "evaluate_proposal",
]

RISK_ENGINE_VERSION = "1.0.0"
_PRODUCER = "engines.risk"

#: Fixed namespace for deterministic decision ids (UUIDv5 over the inputs hash).
_RISK_NAMESPACE = UUID("a3f6e2d1-4b8c-4f0a-9d3e-2c1b5a7f8e9d")


def _json_default(value: object) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime, time)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (frozenset, set)):
        return sorted(_json_default(item) for item in value)
    raise TypeError(f"cannot canonicalize {type(value).__name__}")


def compute_inputs_hash(
    *,
    proposal: TradeProposal,
    account: AccountState,
    portfolio: PortfolioState,
    snapshot: MarketSnapshot | None,
    strategy: StrategyConfiguration,
    policy: RiskPolicy,
    instrument: Instrument,
) -> str:
    """SHA-256 over the canonical JSON of every decision-relevant input.

    Deterministic across runs and processes (sorted keys, compact separators,
    fixed float-format for Decimals). Only decision-relevant fields are hashed —
    not object identity or provenance.
    """
    canonical: dict[str, object] = {
        "engine_version": RISK_ENGINE_VERSION,
        "proposal": {
            "proposal_id": proposal.proposal_id,
            "strategy_id": proposal.strategy_id,
            "strategy_version": proposal.strategy_version,
            "instrument_id": proposal.instrument_id,
            "operating_mode": proposal.operating_mode,
            "direction": proposal.direction,
            "order_type": proposal.order_type,
            "time_in_force": proposal.time_in_force,
            "quantity": proposal.quantity,
            "limit_price": proposal.limit_price,
            "stop_loss": proposal.stop_loss,
            "take_profit": proposal.take_profit,
            "expires_at": proposal.expires_at,
        },
        "account": {
            "account_id": account.account_id,
            "currency": account.currency,
            "balance": account.balance,
            "equity": account.equity,
            "free_margin": account.free_margin,
            "leverage": account.leverage,
            "peak_equity": account.peak_equity,
            "daily_pnl": account.daily_pnl,
            "consecutive_losses": account.consecutive_losses,
            "last_loss_at": account.last_loss_at,
            "broker_connected": account.broker_connected,
            "last_heartbeat_at": account.last_heartbeat_at,
            "safe_mode": account.safe_mode,
            "as_of": account.as_of,
        },
        "portfolio": {
            "account_id": portfolio.account_id,
            "pending_order_count": portfolio.pending_order_count,
            "positions": [
                {
                    "position_id": p.position_id,
                    "instrument_id": p.instrument_id,
                    "side": p.side,
                    "quantity": p.quantity,
                    "average_entry_price": p.average_entry_price,
                    "mark_price": p.mark_price,
                }
                for p in portfolio.positions
            ],
            "exposure": {
                "total_notional": portfolio.exposure.total_notional,
                "by_instrument": portfolio.exposure.by_instrument,
                "by_asset_class": portfolio.exposure.by_asset_class,
                "net_by_currency": portfolio.exposure.net_by_currency,
            },
            "as_of": portfolio.as_of,
        },
        "snapshot": None
        if snapshot is None
        else {
            "instrument_id": snapshot.instrument_id,
            "as_of": snapshot.as_of,
            "source_timestamp": snapshot.source_timestamp,
            "bid": snapshot.bid,
            "ask": snapshot.ask,
        },
        "strategy": {
            "strategy_id": strategy.strategy_id,
            "strategy_version": strategy.strategy_version,
            "enabled": strategy.enabled,
            "state": strategy.state,
            "allowed_instruments": strategy.allowed_instruments,
            "as_of": strategy.as_of,
        },
        "instrument": {
            "instrument_id": instrument.instrument_id,
            "asset_class": instrument.asset_class,
            "base_currency": instrument.base_currency,
            "quote_currency": instrument.quote_currency,
            "contract_size": instrument.contract_size,
            "tick_size": instrument.tick_size,
            "lot_size": instrument.lot_size,
            "lot_step": instrument.lot_step,
            "min_lot": instrument.min_lot,
            "max_lot": instrument.max_lot,
            "is_active": instrument.is_active,
        },
        "policy": {
            "policy_id": policy.policy_id,
            "policy_version": policy.policy_version,
            "max_risk_per_trade": policy.max_risk_per_trade,
            "strategy_risk_budgets": policy.strategy_risk_budgets,
            "max_total_exposure": policy.max_total_exposure,
            "max_instrument_exposure": policy.max_instrument_exposure,
            "max_asset_class_exposure": policy.max_asset_class_exposure,
            "max_currency_exposure": policy.max_currency_exposure,
            "max_leverage": policy.max_leverage,
            "margin_rates": policy.margin_rates,
            "max_positions": policy.max_positions,
            "max_pending_orders": policy.max_pending_orders,
            "max_daily_loss": policy.max_daily_loss,
            "max_drawdown_pct": policy.max_drawdown_pct,
            "max_consecutive_losses": policy.max_consecutive_losses,
            "cooldown_seconds": policy.cooldown_seconds,
            "max_spread_relative": policy.max_spread_relative,
            "max_slippage_relative": policy.max_slippage_relative,
            "min_stop_distance": policy.min_stop_distance,
            "market_data_max_age_seconds": policy.market_data_max_age_seconds,
            "heartbeat_max_age_seconds": policy.heartbeat_max_age_seconds,
            "min_position_size": policy.min_position_size,
            "max_position_size": policy.max_position_size,
            "instrument_whitelist": policy.instrument_whitelist,
            "trading_days": policy.trading_days,
            "session_open_utc": policy.session_open_utc,
            "session_close_utc": policy.session_close_utc,
        },
    }
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=_json_default)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _dedupe(codes: Sequence[RiskReasonCode]) -> list[RiskReasonCode]:
    seen: set[RiskReasonCode] = set()
    unique: list[RiskReasonCode] = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            unique.append(code)
    return unique


def _validate_inputs(
    *,
    proposal: TradeProposal,
    account: AccountState,
    portfolio: PortfolioState,
    snapshot: MarketSnapshot | None,
    strategy: StrategyConfiguration,
    instrument: Instrument,
) -> datetime:
    if instrument.instrument_id != proposal.instrument_id:
        raise RiskEngineInputError(
            f"instrument {instrument.instrument_id!r} does not match proposal "
            f"instrument {proposal.instrument_id!r}"
        )
    if account.account_id != portfolio.account_id:
        raise RiskEngineInputError("account and portfolio must belong to the same account")
    if snapshot is not None and snapshot.instrument_id != proposal.instrument_id:
        raise RiskEngineInputError(
            f"snapshot instrument {snapshot.instrument_id!r} does not match proposal "
            f"instrument {proposal.instrument_id!r}"
        )
    now = snapshot.as_of if snapshot is not None else account.as_of
    for label, state_as_of in (
        ("account", account.as_of),
        ("portfolio", portfolio.as_of),
        ("strategy", strategy.as_of),
    ):
        if state_as_of > now:
            raise RiskEngineInputError(
                f"{label} as_of {state_as_of.isoformat()} is in the future relative "
                f"to evaluation time {now.isoformat()} (INV-3)"
            )
    return now


class RiskEngine:
    """Stateless deterministic Risk & Policy Engine (pure function of inputs)."""

    def evaluate(
        self,
        *,
        proposal: TradeProposal,
        account: AccountState,
        portfolio: PortfolioState,
        snapshot: MarketSnapshot | None,
        strategy: StrategyConfiguration,
        policy: RiskPolicy,
        instrument: Instrument,
    ) -> RiskDecision:
        """Evaluate one proposal and return a deterministic ``RiskDecision``."""
        now = _validate_inputs(
            proposal=proposal,
            account=account,
            portfolio=portfolio,
            snapshot=snapshot,
            strategy=strategy,
            instrument=instrument,
        )

        hard_reasons = run_hard_checks(
            proposal=proposal,
            account=account,
            portfolio=portfolio,
            snapshot=snapshot,
            strategy=strategy,
            policy=policy,
            instrument_is_active=instrument.is_active,
            now=now,
        )

        inputs_hash = compute_inputs_hash(
            proposal=proposal,
            account=account,
            portfolio=portfolio,
            snapshot=snapshot,
            strategy=strategy,
            policy=policy,
            instrument=instrument,
        )

        if hard_reasons:
            return self._decision(
                decision_type=RiskDecisionType.REJECT,
                reason_codes=hard_reasons,
                approved_quantity=None,
                approved_stop=None,
                risk_amount=None,
                proposal=proposal,
                policy=policy,
                now=now,
                inputs_hash=inputs_hash,
            )

        assert snapshot is not None  # snapshot is None is always a hard violation
        plan = compute_size_plan(
            proposal=proposal,
            account=account,
            portfolio=portfolio,
            snapshot=snapshot,
            strategy=strategy,
            policy=policy,
            instrument=instrument,
        )

        if plan.below_minimum:
            reason_codes = _dedupe([*plan.binding_codes, RiskReasonCode.SIZE_BELOW_MINIMUM])
            return self._decision(
                decision_type=RiskDecisionType.REJECT,
                reason_codes=reason_codes,
                approved_quantity=None,
                approved_stop=None,
                risk_amount=None,
                proposal=proposal,
                policy=policy,
                now=now,
                inputs_hash=inputs_hash,
            )

        risk_amount = plan.final_quantity * plan.risk_per_lot
        if plan.final_quantity == proposal.quantity:
            return self._decision(
                decision_type=RiskDecisionType.APPROVE,
                reason_codes=[],
                approved_quantity=plan.final_quantity,
                approved_stop=proposal.stop_loss,
                risk_amount=risk_amount,
                proposal=proposal,
                policy=policy,
                now=now,
                inputs_hash=inputs_hash,
            )

        return self._decision(
            decision_type=RiskDecisionType.RESIZE,
            reason_codes=_dedupe(plan.binding_codes),
            approved_quantity=plan.final_quantity,
            approved_stop=proposal.stop_loss,
            risk_amount=risk_amount,
            proposal=proposal,
            policy=policy,
            now=now,
            inputs_hash=inputs_hash,
        )

    @staticmethod
    def _decision(
        *,
        decision_type: RiskDecisionType,
        reason_codes: list[RiskReasonCode],
        approved_quantity: Decimal | None,
        approved_stop: Decimal | None,
        risk_amount: Decimal | None,
        proposal: TradeProposal,
        policy: RiskPolicy,
        now: datetime,
        inputs_hash: str,
    ) -> RiskDecision:
        decision_id = uuid5(_RISK_NAMESPACE, inputs_hash)
        provenance = Provenance(
            producer=_PRODUCER,
            produced_at=now,
            code_version=RISK_ENGINE_VERSION,
            source_ids={
                "proposal_id": str(proposal.proposal_id),
                "policy_id": policy.policy_id,
                "strategy_id": proposal.strategy_id,
            },
        )
        return RiskDecision(
            decision_id=decision_id,
            proposal_id=proposal.proposal_id,
            decision=decision_type,
            reason_codes=reason_codes,
            approved_quantity=approved_quantity,
            approved_stop=approved_stop,
            risk_amount=risk_amount,
            policy_version=policy.policy_version,
            risk_engine_version=RISK_ENGINE_VERSION,
            inputs_hash=inputs_hash,
            produced_at=now,
            provenance=provenance,
            trace_id=proposal.trace_id,
        )


def evaluate_proposal(
    *,
    proposal: TradeProposal,
    account: AccountState,
    portfolio: PortfolioState,
    snapshot: MarketSnapshot | None,
    strategy: StrategyConfiguration,
    policy: RiskPolicy,
    instrument: Instrument,
) -> RiskDecision:
    """Convenience wrapper around :class:`RiskEngine` for the pipeline."""
    return RiskEngine().evaluate(
        proposal=proposal,
        account=account,
        portfolio=portfolio,
        snapshot=snapshot,
        strategy=strategy,
        policy=policy,
        instrument=instrument,
    )
