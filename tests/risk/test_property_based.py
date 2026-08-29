"""Property-based tests (Hypothesis) for the deterministic Risk Engine.

Properties enforced for arbitrary inputs:

1. Engine never raises on valid inputs; decision is always well-shaped.
2. APPROVE keeps the proposed quantity; RESIZE never exceeds it.
3. Approved risk <= effective risk budget (exact arithmetic).
4. Every approved size satisfies every soft limit exactly (no bypass).
5. Blocking invariants hold unconditionally (daily loss, stale data, disabled).
6. Determinism: identical inputs → identical decisions and reason codes.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from core.domain.enums import (
    AssetClass,
    OrderType,
    RiskDecisionType,
    SignalDirection,
    StrategyState,
)
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.strategies import composite

from risk_helpers import (
    CONTRACT_SIZE,
    MID,
    T0,
    build_account,
    build_instrument,
    build_policy,
    build_portfolio,
    build_proposal,
    build_snapshot,
    build_strategy,
    make_position,
)

APPROVE = RiskDecisionType.APPROVE
RESIZE = RiskDecisionType.RESIZE
REJECT = RiskDecisionType.REJECT

LOT_STEP = Decimal("0.01")
MIN_LOT = Decimal("0.01")
DRAWN_INSTRUMENT = build_instrument(T0)


@composite
def engine_inputs(draw):
    """Generate one arbitrary (but contract-valid) engine input bundle."""
    direction = draw(st.sampled_from([SignalDirection.LONG, SignalDirection.SHORT]))
    order_type = draw(st.sampled_from([OrderType.MARKET, OrderType.LIMIT]))
    quantity = draw(st.decimals(min_value="0.005", max_value="25", places=3))
    has_stop = draw(st.booleans())

    bid = draw(st.decimals(min_value="0.5", max_value="2.0", places=5))
    spread_abs = draw(st.decimals(min_value="0.00001", max_value="0.005", places=5))
    ask = bid + spread_abs
    mid = (bid + ask) / 2

    stop_distance = draw(st.decimals(min_value="0.00005", max_value="0.02", places=5))
    stop_loss = None
    limit_price = None
    if has_stop:
        if direction is SignalDirection.LONG:
            stop_loss = mid - stop_distance
        else:
            stop_loss = mid + stop_distance
    if order_type is OrderType.LIMIT:
        offset = draw(st.decimals(min_value="-0.001", max_value="0.001", places=5))
        limit_price = mid + offset
        if limit_price <= 0:
            limit_price = mid

    snapshot_age = draw(st.integers(min_value=0, max_value=120))
    heartbeat_age = draw(st.integers(min_value=0, max_value=120))
    broker_connected = draw(st.booleans())
    safe_mode = draw(st.booleans())
    enabled = draw(st.booleans())
    strategy_state = draw(st.sampled_from(list(StrategyState)))
    whitelist = draw(
        st.sampled_from([None, frozenset({"EURUSD"}), frozenset({"GBPUSD"}), frozenset()])
    )

    equity = draw(st.decimals(min_value="1000", max_value="1000000", places=2))
    free_margin = draw(st.decimals(min_value="0", max_value="1000000", places=2))
    peak_equity = draw(st.decimals(min_value="1000", max_value="2000000", places=2))
    daily_pnl = draw(st.decimals(min_value="-50000", max_value="5000", places=2))
    consecutive_losses = draw(st.integers(min_value=0, max_value=5))
    last_loss_at = (
        T0 - timedelta(seconds=draw(st.integers(min_value=0, max_value=600)))
        if consecutive_losses > 0
        else None
    )

    max_daily_loss = draw(st.decimals(min_value="100", max_value="50000", places=2))
    max_drawdown_pct = draw(st.decimals(min_value="0.05", max_value="0.9", places=4))
    max_consecutive_losses = draw(st.integers(min_value=1, max_value=5))
    cooldown_seconds = draw(st.integers(min_value=0, max_value=3600))
    max_risk_per_trade = draw(st.decimals(min_value="1", max_value="50000", places=2))
    strategy_budget = draw(st.decimals(min_value="1", max_value="50000", places=2))
    max_total_exposure = draw(st.decimals(min_value="1000", max_value="100000000", places=2))
    max_instrument_exposure = draw(st.decimals(min_value="1000", max_value="5000000", places=2))
    class_limit = draw(st.decimals(min_value="1000", max_value="100000000", places=2))
    currency_limit_eur = draw(st.decimals(min_value="1000", max_value="100000000", places=2))
    currency_limit_usd = draw(st.decimals(min_value="1000", max_value="100000000", places=2))
    max_leverage = draw(st.decimals(min_value="1", max_value="100", places=4))
    margin_rate = draw(st.decimals(min_value="0.01", max_value="0.5", places=4))
    min_stop_distance = draw(st.decimals(min_value="0.0001", max_value="0.002", places=4))
    max_spread_relative = draw(st.decimals(min_value="0.0001", max_value="0.01", places=5))
    max_slippage_relative = draw(st.decimals(min_value="0.0001", max_value="0.01", places=5))
    market_data_max_age = draw(st.integers(min_value=1, max_value=120))
    heartbeat_max_age = draw(st.integers(min_value=0, max_value=120))

    policy_size_min = draw(
        st.one_of(st.none(), st.decimals(min_value="0.01", max_value="2", places=2))
    )
    policy_size_max = draw(
        st.one_of(
            st.none(),
            st.decimals(
                min_value=str(policy_size_min if policy_size_min is not None else "0.01"),
                max_value="5",
                places=2,
            ),
        )
    )

    # portfolio with 0..3 positions on instruments other than EURUSD
    n_positions = draw(st.integers(min_value=0, max_value=3))
    positions: list[Any] = []
    by_instrument: dict[str, Decimal] = {}
    for index in range(n_positions):
        instrument_id = f"AUX{index}"
        position_qty = draw(st.decimals(min_value="0.01", max_value="5", places=2))
        position_price = draw(st.decimals(min_value="0.5", max_value="2.0", places=5))
        positions.append(
            make_position(
                T0,
                f"pos-{index}",
                instrument_id,
                "LONG" if index % 2 == 0 else "SHORT",
                position_qty,
                position_price,
            )
        )
        by_instrument[instrument_id] = position_qty * CONTRACT_SIZE * position_price
    pending_order_count = draw(st.integers(min_value=0, max_value=8))
    max_positions = draw(st.integers(min_value=1, max_value=6))
    max_pending_orders = draw(st.integers(min_value=1, max_value=10))

    policy = build_policy(
        T0,
        max_risk_per_trade=max_risk_per_trade,
        strategy_risk_budgets={"strategy-01": strategy_budget},
        max_total_exposure=max_total_exposure,
        max_instrument_exposure=max_instrument_exposure,
        max_asset_class_exposure={AssetClass.FX: class_limit},
        max_currency_exposure={
            "EUR": currency_limit_eur,
            "USD": currency_limit_usd,
        },
        max_leverage=max_leverage,
        margin_rates={AssetClass.FX: margin_rate},
        max_positions=max_positions,
        max_pending_orders=max_pending_orders,
        max_daily_loss=max_daily_loss,
        max_drawdown_pct=max_drawdown_pct,
        max_consecutive_losses=max_consecutive_losses,
        cooldown_seconds=cooldown_seconds,
        max_spread_relative=max_spread_relative,
        max_slippage_relative=max_slippage_relative,
        min_stop_distance=min_stop_distance,
        market_data_max_age_seconds=market_data_max_age,
        heartbeat_max_age_seconds=heartbeat_max_age,
        min_position_size=policy_size_min,
        max_position_size=policy_size_max,
        instrument_whitelist=whitelist,
    )
    proposal = build_proposal(
        T0,
        direction=direction,
        order_type=order_type,
        quantity=quantity,
        stop_loss=stop_loss,
        limit_price=limit_price,
    )
    snapshot = build_snapshot(
        T0,
        bid=bid,
        ask=ask,
        source_timestamp=T0 - timedelta(seconds=snapshot_age),
    )
    account = build_account(
        T0,
        equity=equity,
        free_margin=free_margin,
        peak_equity=peak_equity,
        daily_pnl=daily_pnl,
        consecutive_losses=consecutive_losses,
        last_loss_at=last_loss_at,
        broker_connected=broker_connected,
        last_heartbeat_at=T0 - timedelta(seconds=heartbeat_age),
        safe_mode=safe_mode,
    )
    strategy = build_strategy(T0, enabled=enabled, state=strategy_state)
    portfolio = _with_exposure(positions, by_instrument, pending_order_count)
    return {
        "proposal": proposal,
        "account": account,
        "portfolio": portfolio,
        "snapshot": snapshot,
        "strategy": strategy,
        "policy": policy,
        "instrument": DRAWN_INSTRUMENT,
    }


def _with_exposure(
    positions: list[Any], by_instrument: dict[str, Decimal], pending_order_count: int
):
    from core.schemas.risk import PortfolioExposure

    total = sum(by_instrument.values(), Decimal("0"))
    return build_portfolio(
        T0,
        positions=positions,
        pending_order_count=pending_order_count,
        exposure=PortfolioExposure(
            total_notional=total,
            by_instrument=dict(by_instrument),
            by_asset_class={AssetClass.FX: total},
        ),
    )


def _evaluate(bundle: dict[str, Any]):
    from engines.risk import evaluate_proposal

    return evaluate_proposal(**bundle)


def _effective_budget(bundle: dict[str, Any]) -> Decimal:
    policy = bundle["policy"]
    return min(
        policy.max_risk_per_trade,
        policy.strategy_risk_budgets.get("strategy-01", policy.max_risk_per_trade),
    )


def _entry_price(bundle: dict[str, Any]) -> Decimal:
    proposal = bundle["proposal"]
    return proposal.limit_price if proposal.limit_price is not None else MID


@settings(max_examples=300, deadline=None)
@given(engine_inputs())
def test_decision_is_well_shaped_and_never_raises(bundle: dict[str, Any]) -> None:
    decision = _evaluate(bundle)
    if decision.decision is APPROVE:
        assert decision.reason_codes == []
        assert decision.approved_quantity == bundle["proposal"].quantity
        assert decision.approved_stop is not None
        assert decision.risk_amount is not None
    elif decision.decision is RESIZE:
        assert decision.reason_codes
        assert decision.approved_quantity is not None
        assert 0 < decision.approved_quantity <= bundle["proposal"].quantity
        assert decision.approved_stop is not None
        assert decision.risk_amount is not None
    else:
        assert decision.decision is REJECT
        assert decision.reason_codes
        assert decision.approved_quantity is None
        assert decision.approved_stop is None
        assert decision.risk_amount is None


@settings(max_examples=300, deadline=None)
@given(engine_inputs())
def test_approved_risk_and_size_respect_every_soft_limit(bundle: dict[str, Any]) -> None:
    decision = _evaluate(bundle)
    if decision.decision not in (APPROVE, RESIZE):
        return
    proposal = bundle["proposal"]
    policy = bundle["policy"]
    account = bundle["account"]
    exposure = bundle["portfolio"].exposure
    quantity = decision.approved_quantity
    assert quantity is not None

    # exact arithmetic — same guarantees the engine enforces
    entry = _entry_price(bundle)
    distance = abs(entry - proposal.stop_loss)
    notional = quantity * CONTRACT_SIZE * entry
    risk = quantity * CONTRACT_SIZE * distance

    assert risk <= _effective_budget(bundle)
    assert decision.risk_amount == risk
    assert decision.approved_stop == proposal.stop_loss

    assert notional + exposure.total_notional <= policy.max_total_exposure
    assert (
        notional + exposure.by_instrument.get(proposal.instrument_id, Decimal("0"))
        <= policy.max_instrument_exposure
    )
    assert notional + exposure.by_asset_class.get(
        AssetClass.FX, Decimal("0")
    ) <= policy.max_asset_class_exposure.get(AssetClass.FX, Decimal("0"))
    assert notional + exposure.total_notional <= policy.max_leverage * account.equity
    assert notional * policy.margin_rates[AssetClass.FX] <= account.free_margin

    legs = (
        [("EUR", 1), ("USD", -1)]
        if proposal.direction is SignalDirection.LONG
        else [("EUR", -1), ("USD", 1)]
    )
    for currency, sign in legs:
        net = exposure.net_by_currency.get(currency, Decimal("0"))
        assert abs(net + sign * notional) <= policy.max_currency_exposure[currency]

    max_effective = min(
        (
            policy.max_position_size
            if policy.max_position_size is not None
            else DRAWN_INSTRUMENT.max_lot
        ),
        DRAWN_INSTRUMENT.max_lot,
    )
    min_effective = max(
        policy.min_position_size if policy.min_position_size is not None else Decimal("0"),
        MIN_LOT,
    )
    assert quantity <= max_effective
    assert quantity >= min_effective
    assert quantity % LOT_STEP == 0


@settings(max_examples=300, deadline=None)
@given(engine_inputs())
def test_proposed_risk_above_budget_never_approves(bundle: dict[str, Any]) -> None:
    decision = _evaluate(bundle)
    proposal = bundle["proposal"]
    if proposal.stop_loss is None:
        return
    entry = _entry_price(bundle)
    distance = abs(entry - proposal.stop_loss)
    proposed_risk = proposal.quantity * CONTRACT_SIZE * distance
    budget = _effective_budget(bundle)
    if proposed_risk <= budget:
        return
    assert decision.decision is not APPROVE
    if decision.decision is RESIZE:
        assert decision.risk_amount <= budget


@settings(max_examples=300, deadline=None)
@given(engine_inputs())
def test_blocking_invariants_hold_unconditionally(bundle: dict[str, Any]) -> None:
    decision = _evaluate(bundle)
    account = bundle["account"]
    policy = bundle["policy"]
    snapshot = bundle["snapshot"]
    strategy = bundle["strategy"]

    if account.daily_pnl <= -policy.max_daily_loss:
        assert decision.decision is REJECT
        assert decision.approved_quantity is None
    if (snapshot.as_of - snapshot.source_timestamp).total_seconds() > (
        policy.market_data_max_age_seconds
    ):
        assert decision.decision is REJECT
        assert decision.approved_quantity is None
    if not strategy.enabled:
        assert decision.decision is REJECT
        assert decision.approved_quantity is None


@settings(max_examples=200, deadline=None)
@given(engine_inputs())
def test_deterministic_same_inputs_same_decision(bundle: dict[str, Any]) -> None:
    first = _evaluate(bundle)
    second = _evaluate(bundle)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.decision_id == second.decision_id
    assert first.inputs_hash == second.inputs_hash
    assert first.reason_codes == second.reason_codes
