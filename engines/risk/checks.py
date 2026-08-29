"""Hard (fail-closed) policy checks for the deterministic Risk Engine (INV-4).

Hard checks can only ever cause a ``REJECT`` — reducing the size never fixes a
hard violation (stale data, disabled strategy, breached daily loss, …).

Every check is a pure function of its inputs; there is no state, no IO, no wall
clock. Evaluation order is canonical (``HARD_CHECK_ORDER``) so reason codes are
deterministic.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, time

from core.domain.enums import (
    OrderType,
    RiskReasonCode,
    SignalDirection,
)
from core.schemas.market import MarketSnapshot
from core.schemas.risk import (
    TRADABLE_STRATEGY_STATES,
    AccountState,
    PortfolioState,
    RiskPolicy,
    StrategyConfiguration,
)
from core.schemas.trading import TradeProposal

__all__ = ["HARD_CHECK_ORDER", "RiskEngineInputError", "run_hard_checks"]


class RiskEngineInputError(ValueError):
    """Raised when engine inputs are structurally inconsistent.

    A hard ``REJECT`` answers "is this trade safe?"; an input error answers "the
    inputs cannot be evaluated at all" (future-dated state, id mismatches). Both
    fail closed — no path reaches APPROVE.
    """


def run_hard_checks(
    *,
    proposal: TradeProposal,
    account: AccountState,
    portfolio: PortfolioState,
    snapshot: MarketSnapshot | None,
    strategy: StrategyConfiguration,
    policy: RiskPolicy,
    instrument_is_active: bool,
    now: datetime,
) -> list[RiskReasonCode]:
    """Evaluate every hard check and return the violated reason codes in
    canonical order (empty list means no hard violation)."""
    reasons: list[RiskReasonCode] = []
    for code, predicate in HARD_CHECK_ORDER:
        if predicate(
            proposal=proposal,
            account=account,
            portfolio=portfolio,
            snapshot=snapshot,
            strategy=strategy,
            policy=policy,
            instrument_is_active=instrument_is_active,
            now=now,
        ):
            reasons.append(code)
    return reasons


# ── checks (each returns True when the rule is violated) ──────────────────────


def _strategy_inactive(proposal: TradeProposal, strategy: StrategyConfiguration) -> bool:
    return (
        proposal.strategy_id != strategy.strategy_id
        or proposal.strategy_version != strategy.strategy_version
        or not strategy.enabled
        or strategy.state not in TRADABLE_STRATEGY_STATES
    )


def _symbol_not_whitelisted(
    proposal: TradeProposal,
    strategy: StrategyConfiguration,
    policy: RiskPolicy,
    instrument_is_active: bool,
) -> bool:
    if not instrument_is_active:
        return True
    if (
        policy.instrument_whitelist is not None
        and proposal.instrument_id not in policy.instrument_whitelist
    ):
        return True
    return (
        strategy.allowed_instruments is not None
        and proposal.instrument_id not in strategy.allowed_instruments
    )


def _stale_quotes(
    snapshot: MarketSnapshot | None, proposal: TradeProposal, policy: RiskPolicy, now: datetime
) -> bool:
    if snapshot is None:
        return True
    age_seconds = (now - snapshot.source_timestamp).total_seconds()
    if age_seconds < 0:
        # Future-dated timestamps (clock skew or mislabeled data) must fail
        # closed: negative age would otherwise bypass the staleness gate.
        return True
    return age_seconds > policy.market_data_max_age_seconds


def _broker_disconnected(account: AccountState) -> bool:
    return not account.broker_connected


def _heartbeat_lost(account: AccountState, policy: RiskPolicy, now: datetime) -> bool:
    if policy.heartbeat_max_age_seconds <= 0:
        return False
    if account.last_heartbeat_at is None:
        return True
    age_seconds = (now - account.last_heartbeat_at).total_seconds()
    return age_seconds > policy.heartbeat_max_age_seconds


def _safe_mode_active(account: AccountState) -> bool:
    return account.safe_mode


def _outside_trading_schedule(policy: RiskPolicy, now: datetime) -> bool:
    if now.weekday() not in policy.trading_days:
        return True
    if policy.session_open_utc is None:
        return False
    if policy.session_close_utc is None:  # policy validator requires both-or-none
        return False
    current: time = now.time().replace(tzinfo=None)
    opens: time = policy.session_open_utc
    closes: time = policy.session_close_utc
    if opens <= closes:  # intraday session
        return not (opens <= current <= closes)
    return not (current >= opens or current <= closes)  # overnight session


def _daily_loss_reached(account: AccountState, policy: RiskPolicy) -> bool:
    return account.daily_pnl <= -policy.max_daily_loss


def _drawdown_reached(account: AccountState, policy: RiskPolicy) -> bool:
    drawdown = (account.peak_equity - account.equity) / account.peak_equity
    return drawdown >= policy.max_drawdown_pct


def _loss_sequence_cooldown(account: AccountState, policy: RiskPolicy, now: datetime) -> bool:
    if account.consecutive_losses < policy.max_consecutive_losses:
        return False
    if account.last_loss_at is None:
        return True  # threshold met but no timestamp: fail closed
    elapsed_seconds = (now - account.last_loss_at).total_seconds()
    return elapsed_seconds < policy.cooldown_seconds


def _max_positions_reached(portfolio: PortfolioState, policy: RiskPolicy) -> bool:
    return len(portfolio.positions) + 1 > policy.max_positions


def _max_orders_reached(portfolio: PortfolioState, policy: RiskPolicy) -> bool:
    return portfolio.pending_order_count + 1 > policy.max_pending_orders


def _spread_too_high(snapshot: MarketSnapshot | None, policy: RiskPolicy) -> bool:
    if snapshot is None:
        return False  # STALE_QUOTES already covers the missing quote
    relative_spread = (snapshot.ask - snapshot.bid) / snapshot.mid
    return relative_spread > policy.max_spread_relative


def _slippage_cap_exceeded(
    proposal: TradeProposal, snapshot: MarketSnapshot | None, policy: RiskPolicy
) -> bool:
    if snapshot is None:
        return False  # STALE_QUOTES already covers the missing quote
    if proposal.order_type is not OrderType.MARKET:
        return False  # limit/stop orders fill at the limit price, not the touch
    if proposal.direction is SignalDirection.LONG:
        worst_fill = snapshot.ask
        relative = (worst_fill - snapshot.mid) / snapshot.mid
    else:
        worst_fill = snapshot.bid
        relative = (snapshot.mid - worst_fill) / snapshot.mid
    return relative > policy.max_slippage_relative


def _invalid_stop_distance(
    proposal: TradeProposal, snapshot: MarketSnapshot | None, policy: RiskPolicy
) -> bool:
    stop = proposal.stop_loss
    if stop is None:
        return True
    if snapshot is None:
        entry = proposal.limit_price
        if entry is None:
            return False  # STALE_QUOTES already fired; nothing to measure against
    else:
        entry = proposal.limit_price if proposal.limit_price is not None else snapshot.mid
    if proposal.direction is SignalDirection.LONG:
        if stop >= entry:
            return True
        distance = entry - stop
    else:
        if stop <= entry:
            return True
        distance = stop - entry
    return distance < policy.min_stop_distance


# ── canonical order (reason codes appear in this order in decisions) ──────────

#: A single hard-check predicate: returns True when the rule is violated.
CheckFn = Callable[..., bool]

#: (reason_code, predicate) pairs evaluated in canonical order.
HARD_CHECK_ORDER: tuple[tuple[RiskReasonCode, CheckFn], ...] = (
    (
        RiskReasonCode.STRATEGY_INACTIVE,
        lambda *, proposal, strategy, **_k: _strategy_inactive(proposal, strategy),
    ),
    (
        RiskReasonCode.SYMBOL_NOT_WHITELISTED,
        lambda *, proposal, strategy, policy, instrument_is_active, **_k: _symbol_not_whitelisted(
            proposal, strategy, policy, instrument_is_active
        ),
    ),
    (
        RiskReasonCode.STALE_QUOTES,
        lambda *, snapshot, proposal, policy, now, **_k: _stale_quotes(
            snapshot, proposal, policy, now
        ),
    ),
    (
        RiskReasonCode.BROKER_DISCONNECTED,
        lambda *, account, **_k: _broker_disconnected(account),
    ),
    (
        RiskReasonCode.HEARTBEAT_LOST,
        lambda *, account, policy, now, **_k: _heartbeat_lost(account, policy, now),
    ),
    (
        RiskReasonCode.SAFE_MODE_ACTIVE,
        lambda *, account, **_k: _safe_mode_active(account),
    ),
    (
        RiskReasonCode.TRADING_HOURS_RESTRICTED,
        lambda *, policy, now, **_k: _outside_trading_schedule(policy, now),
    ),
    (
        RiskReasonCode.MAX_DAILY_LOSS_REACHED,
        lambda *, account, policy, **_k: _daily_loss_reached(account, policy),
    ),
    (
        RiskReasonCode.MAX_DRAWDOWN_REACHED,
        lambda *, account, policy, **_k: _drawdown_reached(account, policy),
    ),
    (
        RiskReasonCode.LOSS_SEQUENCE_COOLDOWN,
        lambda *, account, policy, now, **_k: _loss_sequence_cooldown(account, policy, now),
    ),
    (
        RiskReasonCode.MAX_POSITIONS_REACHED,
        lambda *, portfolio, policy, **_k: _max_positions_reached(portfolio, policy),
    ),
    (
        RiskReasonCode.MAX_ORDERS_REACHED,
        lambda *, portfolio, policy, **_k: _max_orders_reached(portfolio, policy),
    ),
    (
        RiskReasonCode.SPREAD_TOO_HIGH,
        lambda *, snapshot, policy, **_k: _spread_too_high(snapshot, policy),
    ),
    (
        RiskReasonCode.SLIPPAGE_CAP_EXCEEDED,
        lambda *, proposal, snapshot, policy, **_k: _slippage_cap_exceeded(
            proposal, snapshot, policy
        ),
    ),
    (
        RiskReasonCode.INVALID_STOP_DISTANCE,
        lambda *, proposal, snapshot, policy, **_k: _invalid_stop_distance(
            proposal, snapshot, policy
        ),
    ),
)
