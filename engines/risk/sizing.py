"""Deterministic sizing for the Risk Engine (INV-1: the engine decides capital).

The approved quantity is ALWAYS computed here — the proposal's ``quantity`` is
advisory only. For every soft limit a maximum quantity is derived; the final
quantity is the minimum of all caps, floored to the instrument lot step and
clamped to the effective min/max.

Soft (resize-able) limits:

=====================  =============================
Reason code            Limit
=====================  =============================
RISK_LIMIT_EXCEEDED    per-trade risk budget
CONCENTRATION_*        instrument / asset-class / currency exposure
EXPOSURE_LIMIT_*       total exposure
LEVERAGE_LIMIT_*       leverage
INSUFFICIENT_MARGIN    free margin at the asset-class margin rate
SIZE_ABOVE_MAXIMUM     effective maximum size
LOT_STEP_INVALID       lot-step normalization
SIZE_BELOW_MINIMUM     effective minimum size (cannot resize -> REJECT)
=====================  =============================

Notional and risk are denominated in the instrument quote currency (ADR-0018).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from core.domain.enums import RiskReasonCode, SignalDirection
from core.schemas.market import Instrument, MarketSnapshot
from core.schemas.risk import (
    AccountState,
    PortfolioState,
    RiskPolicy,
    StrategyConfiguration,
)
from core.schemas.trading import TradeProposal

__all__ = ["SizingPlan", "compute_size_plan", "floor_to_step"]

_ZERO = Decimal("0")


@dataclass(frozen=True)
class SizingPlan:
    """Outcome of deterministic sizing (see :func:`compute_size_plan`)."""

    final_quantity: Decimal
    min_effective: Decimal
    max_effective: Decimal
    binding_codes: tuple[RiskReasonCode, ...]
    floor_applied: bool
    below_minimum: bool
    entry_price: Decimal
    stop_distance: Decimal
    notional_per_lot: Decimal
    risk_per_lot: Decimal
    effective_risk_budget: Decimal


def floor_to_step(quantity: Decimal, step: Decimal) -> Decimal:
    """Round ``quantity`` down to a multiple of ``step`` (never up — only smaller)."""
    if quantity <= 0:
        return _ZERO
    if step <= 0:
        raise ValueError("lot step must be > 0")
    steps = (quantity / step).to_integral_value(rounding=ROUND_DOWN)
    return (steps * step).quantize(step)


def _soft_limits_ok(
    quantity: Decimal,
    *,
    proposal: TradeProposal,
    instrument: Instrument,
    policy: RiskPolicy,
    portfolio: PortfolioState,
    account: AccountState,
    budget: Decimal,
    entry: Decimal,
    stop_distance: Decimal,
    margin_rate: Decimal,
    max_effective: Decimal,
) -> bool:
    """Exact-arithmetic verification that ``quantity`` respects every soft limit.

    Caps are derived by division (28-significant-digit rounding); this final gate
    re-checks each limit with exact multiplication/addition so even a one-ulp
    rounding of a cap can never let a size through.
    """
    if quantity > max_effective:
        return False
    notional = instrument.contract_size * quantity * entry
    risk = instrument.contract_size * quantity * stop_distance
    if risk > budget:
        return False
    exposure = portfolio.exposure
    if (
        notional + exposure.by_instrument.get(proposal.instrument_id, _ZERO)
        > policy.max_instrument_exposure
    ):
        return False
    asset_class = instrument.asset_class
    if notional + exposure.by_asset_class.get(
        asset_class, _ZERO
    ) > policy.max_asset_class_exposure.get(asset_class, _ZERO):
        return False
    if notional + exposure.total_notional > policy.max_total_exposure:
        return False
    if notional + exposure.total_notional > policy.max_leverage * account.equity:
        return False
    if notional * margin_rate > account.free_margin:
        return False
    for currency, sign in _currency_legs(proposal, instrument):
        if currency is None:
            return False
        limit = policy.max_currency_exposure.get(currency, _ZERO)
        net = exposure.net_by_currency.get(currency, _ZERO)
        if abs(net + sign * notional) > limit:
            return False
    return True


def _currency_legs(
    proposal: TradeProposal, instrument: Instrument
) -> tuple[tuple[str | None, int], ...]:
    if proposal.direction is SignalDirection.LONG:
        return (instrument.base_currency, 1), (instrument.quote_currency, -1)
    return (instrument.base_currency, -1), (instrument.quote_currency, 1)


def _max_currency_notional(
    proposal: TradeProposal,
    instrument: Instrument,
    policy: RiskPolicy,
    net_by_currency: dict[str, Decimal],
) -> Decimal:
    """Max additional notional allowed by currency-exposure limits (net notional).

    A LONG adds +notional to the base currency and -notional to the quote
    currency; a SHORT reverses both. Every leg must stay within its limit.
    """
    allowed_by_leg: list[Decimal] = []
    for currency, sign in _currency_legs(proposal, instrument):
        if currency is None:
            allowed_by_leg.append(_ZERO)  # unknown currency: fail closed
            continue
        limit = policy.max_currency_exposure.get(currency, _ZERO)
        net = net_by_currency.get(currency, _ZERO)
        # |net + sign * n| <= limit  →  n <= limit - sign * net
        allowed_by_leg.append(limit - sign * net)
    allowed = min(allowed_by_leg)
    return allowed if allowed > 0 else _ZERO


def compute_size_plan(
    *,
    proposal: TradeProposal,
    account: AccountState,
    portfolio: PortfolioState,
    snapshot: MarketSnapshot,
    strategy: StrategyConfiguration,
    policy: RiskPolicy,
    instrument: Instrument,
) -> SizingPlan:
    """Compute the approved quantity for a proposal that passed all hard checks."""
    stop = proposal.stop_loss
    if stop is None:
        # Unreachable when hard checks ran (INVALID_STOP_DISTANCE); kept fail-closed.
        raise ValueError("a stop loss is required to compute a size (INV-4)")

    entry = proposal.limit_price if proposal.limit_price is not None else snapshot.mid
    stop_distance = abs(entry - stop)
    notional_per_lot = instrument.contract_size * entry
    risk_per_lot = instrument.contract_size * stop_distance

    budget = min(
        policy.max_risk_per_trade,
        policy.strategy_risk_budgets.get(proposal.strategy_id, policy.max_risk_per_trade),
    )

    exposure = portfolio.exposure
    asset_class = instrument.asset_class
    margin_rate = policy.margin_rates.get(asset_class)
    if margin_rate is None:
        margin_rate = _ZERO  # class not admitted by policy: no margin allowance

    max_effective = min(
        policy.max_position_size if policy.max_position_size is not None else instrument.max_lot,
        instrument.max_lot,
    )
    min_effective = max(
        policy.min_position_size if policy.min_position_size is not None else _ZERO,
        instrument.min_lot,
    )

    current_instrument = exposure.by_instrument.get(proposal.instrument_id, _ZERO)
    current_class = exposure.by_asset_class.get(asset_class, _ZERO)

    caps: list[tuple[RiskReasonCode, Decimal]] = [
        (
            RiskReasonCode.RISK_LIMIT_EXCEEDED,
            budget / risk_per_lot,
        ),
        (
            RiskReasonCode.CONCENTRATION_LIMIT_EXCEEDED,
            (policy.max_instrument_exposure - current_instrument) / notional_per_lot,
        ),
        (
            RiskReasonCode.CONCENTRATION_LIMIT_EXCEEDED,
            (policy.max_asset_class_exposure.get(asset_class, _ZERO) - current_class)
            / notional_per_lot,
        ),
        (
            RiskReasonCode.CONCENTRATION_LIMIT_EXCEEDED,
            _max_currency_notional(proposal, instrument, policy, exposure.net_by_currency)
            / notional_per_lot,
        ),
        (
            RiskReasonCode.EXPOSURE_LIMIT_EXCEEDED,
            (policy.max_total_exposure - exposure.total_notional) / notional_per_lot,
        ),
        (
            RiskReasonCode.LEVERAGE_LIMIT_EXCEEDED,
            (policy.max_leverage * account.equity - exposure.total_notional) / notional_per_lot,
        ),
        (
            RiskReasonCode.INSUFFICIENT_MARGIN,
            account.free_margin / (notional_per_lot * margin_rate) if margin_rate > 0 else _ZERO,
        ),
        (
            RiskReasonCode.SIZE_ABOVE_MAXIMUM,
            max_effective,
        ),
    ]
    caps = [(code, cap if cap > 0 else _ZERO) for code, cap in caps]

    target = proposal.quantity
    for _, cap in caps:
        if cap < target:
            target = cap

    binding_codes: list[RiskReasonCode] = [code for code, cap in caps if cap < proposal.quantity]

    floor_applied = False
    final_quantity = floor_to_step(target, instrument.lot_step)
    if final_quantity < target:
        floor_applied = True

    # Exact gate: walk the size down one lot step at a time until every soft
    # limit holds with exact arithmetic. This is what makes
    # "approved size cannot bypass a configured limit" true, not approximate.
    while True:
        if final_quantity < min_effective:
            break
        if _soft_limits_ok(
            final_quantity,
            proposal=proposal,
            instrument=instrument,
            policy=policy,
            portfolio=portfolio,
            account=account,
            budget=budget,
            entry=entry,
            stop_distance=stop_distance,
            margin_rate=margin_rate,
            max_effective=max_effective,
        ):
            break
        final_quantity = (final_quantity - instrument.lot_step).quantize(instrument.lot_step)

    below_minimum = final_quantity < min_effective
    if floor_applied:
        binding_codes.append(RiskReasonCode.LOT_STEP_INVALID)

    return SizingPlan(
        final_quantity=final_quantity,
        min_effective=min_effective,
        max_effective=max_effective,
        binding_codes=tuple(binding_codes),
        floor_applied=floor_applied,
        below_minimum=below_minimum,
        entry_price=entry,
        stop_distance=stop_distance,
        notional_per_lot=notional_per_lot,
        risk_per_lot=risk_per_lot,
        effective_risk_budget=budget,
    )
