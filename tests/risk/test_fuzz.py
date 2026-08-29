"""Seeded fuzz tests: thousands of adversarial input combinations.

The fuzzer randomizes every decision-relevant input (quantities, stops, prices,
limits, account state) and asserts the engine invariants hold for every single
draw — no path may bypass a configured limit.
"""

from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal

from core.domain.enums import (
    AssetClass,
    OrderType,
    RiskDecisionType,
    SignalDirection,
    StrategyState,
)

from risk_helpers import (
    CONTRACT_SIZE,
    LOT_STEP,
    T0,
    build_account,
    build_instrument,
    build_policy,
    build_portfolio,
    build_proposal,
    build_snapshot,
    build_strategy,
)

APPROVE = RiskDecisionType.APPROVE
RESIZE = RiskDecisionType.RESIZE
REJECT = RiskDecisionType.REJECT

SEED = 20260826
ITERATIONS = 1500
_MIN_LOT = Decimal("0.01")


def _dec(rng: random.Random, lo: str, hi: str, places: int) -> Decimal:
    scale = Decimal(10) ** places
    lo_int = int(Decimal(lo) * scale)
    hi_int = int(Decimal(hi) * scale)
    return Decimal(rng.randint(lo_int, hi_int)) / scale


def _random_inputs(rng: random.Random) -> dict:
    direction = rng.choice([SignalDirection.LONG, SignalDirection.SHORT])
    order_type = rng.choice([OrderType.MARKET, OrderType.LIMIT])
    bid = _dec(rng, "0.5", "2.0", 5)
    spread_abs = _dec(rng, "0.00001", "0.005", 5)
    ask = bid + spread_abs
    mid = (bid + ask) / 2
    stop_distance = _dec(rng, "0.00005", "0.02", 5)
    stop_loss = mid - stop_distance if direction is SignalDirection.LONG else mid + stop_distance
    limit_price = None
    if order_type is OrderType.LIMIT:
        limit_price = mid + _dec(rng, "-0.001", "0.001", 5)
    quantity = _dec(rng, "0.005", "100", rng.choice([2, 3, 4]))

    account = build_account(
        T0,
        equity=_dec(rng, "1000", "1000000", 2),
        free_margin=_dec(rng, "0", "1000000", 2),
        peak_equity=_dec(rng, "1000", "2000000", 2),
        daily_pnl=_dec(rng, "-50000", "5000", 2),
        consecutive_losses=rng.randint(0, 6),
        last_loss_at=T0 - timedelta(seconds=rng.randint(0, 900)),
        broker_connected=rng.random() < 0.9,
        last_heartbeat_at=T0 - timedelta(seconds=rng.randint(0, 180)),
        safe_mode=rng.random() < 0.05,
    )
    account = account.model_copy(
        update={"last_loss_at": None}
        if account.consecutive_losses == 0
        else {"last_loss_at": account.last_loss_at}
    )

    policy = build_policy(
        T0,
        max_risk_per_trade=_dec(rng, "1", "50000", 2),
        strategy_risk_budgets={"strategy-01": _dec(rng, "1", "50000", 2)},
        max_total_exposure=_dec(rng, "1000", "100000000", 2),
        max_instrument_exposure=_dec(rng, "1000", "5000000", 2),
        max_asset_class_exposure={AssetClass.FX: _dec(rng, "1000", "100000000", 2)},
        max_currency_exposure={
            "EUR": _dec(rng, "1000", "100000000", 2),
            "USD": _dec(rng, "1000", "100000000", 2),
        },
        max_leverage=_dec(rng, "1", "100", 4),
        margin_rates={AssetClass.FX: _dec(rng, "0.01", "0.5", 4)},
        max_positions=rng.randint(1, 6),
        max_pending_orders=rng.randint(1, 10),
        max_daily_loss=_dec(rng, "100", "50000", 2),
        max_drawdown_pct=_dec(rng, "0.05", "0.9", 4),
        max_consecutive_losses=rng.randint(1, 5),
        cooldown_seconds=rng.randint(0, 3600),
        max_spread_relative=_dec(rng, "0.0001", "0.01", 5),
        max_slippage_relative=_dec(rng, "0.0001", "0.01", 5),
        min_stop_distance=_dec(rng, "0.0001", "0.002", 4),
        market_data_max_age_seconds=rng.randint(1, 120),
        heartbeat_max_age_seconds=rng.randint(0, 120),
        max_position_size=_dec(rng, "0.01", "5", 2),
        instrument_whitelist=rng.choice([None, frozenset({"EURUSD"}), frozenset({"GBPUSD"})]),
    )

    snapshot = build_snapshot(
        T0,
        bid=bid,
        ask=ask,
        source_timestamp=T0 - timedelta(seconds=rng.randint(0, 180)),
    )
    return {
        "proposal": build_proposal(
            T0,
            direction=direction,
            order_type=order_type,
            quantity=quantity,
            stop_loss=stop_loss,
            limit_price=limit_price,
        ),
        "account": account,
        "portfolio": build_portfolio(T0, pending_order_count=rng.randint(0, 10)),
        "snapshot": snapshot,
        "strategy": build_strategy(
            T0,
            enabled=rng.random() < 0.9,
            state=rng.choice(list(StrategyState)),
        ),
        "policy": policy,
        "instrument": build_instrument(T0),
    }


def _check_one(bundle: dict) -> None:
    from engines.risk import evaluate_proposal

    decision = evaluate_proposal(**bundle)
    proposal = bundle["proposal"]
    policy = bundle["policy"]
    account = bundle["account"]

    # shape invariants
    if decision.decision is APPROVE:
        assert decision.reason_codes == []
        assert decision.approved_quantity == proposal.quantity
        assert decision.approved_quantity is not None
        assert decision.approved_stop is not None
        assert decision.risk_amount is not None
    elif decision.decision is RESIZE:
        assert decision.reason_codes
        assert decision.approved_quantity is not None
        assert decision.approved_quantity <= proposal.quantity
        assert decision.approved_stop is not None
        assert decision.risk_amount is not None
    else:
        assert decision.approved_quantity is None
        assert decision.approved_stop is None
        assert decision.risk_amount is None
        assert decision.reason_codes

    # blocking invariants
    if account.daily_pnl <= -policy.max_daily_loss:
        assert decision.decision is REJECT
    if (snapshot := bundle["snapshot"]).as_of - snapshot.source_timestamp > timedelta(
        seconds=policy.market_data_max_age_seconds
    ):
        assert decision.decision is REJECT
    if not bundle["strategy"].enabled:
        assert decision.decision is REJECT

    # approved risk/size invariants (exact arithmetic)
    if decision.decision in (APPROVE, RESIZE):
        quantity = decision.approved_quantity
        budget = min(
            policy.max_risk_per_trade,
            policy.strategy_risk_budgets.get("strategy-01", policy.max_risk_per_trade),
        )
        entry = (
            proposal.limit_price
            if proposal.limit_price is not None
            else ((bundle["snapshot"].bid + bundle["snapshot"].ask) / 2)
        )
        distance = abs(entry - proposal.stop_loss)
        notional = quantity * CONTRACT_SIZE * entry
        risk = quantity * CONTRACT_SIZE * distance

        assert risk <= budget
        assert decision.risk_amount == risk
        assert notional <= policy.max_total_exposure
        assert notional <= policy.max_leverage * account.equity
        assert notional * policy.margin_rates[AssetClass.FX] <= account.free_margin
        assert quantity <= policy.max_position_size
        assert quantity >= _MIN_LOT
        assert quantity % LOT_STEP == 0


def test_fuzz_invariants_hold_across_thousands_of_inputs() -> None:
    rng = random.Random(SEED)
    for _ in range(ITERATIONS):
        _check_one(_random_inputs(rng))


def test_fuzz_is_deterministic_given_the_seed() -> None:
    first = random.Random(SEED)
    second = random.Random(SEED)
    for _ in range(50):
        a = _random_inputs(first)
        b = _random_inputs(second)
        assert a["proposal"].quantity == b["proposal"].quantity
        assert a["policy"].max_risk_per_trade == b["policy"].max_risk_per_trade
