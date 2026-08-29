"""Shared builders for the Risk Engine test suite (tests/risk/).

Baseline scenario: Monday 10:00 UTC, EURUSD LONG MARKET 0.10 lots, stop at
1.07000 (entry = mid = 1.080025, stop distance 0.010025), contract_size 100000.

Baseline math (contract_size=100000):
- notional per lot = 108002.50
- risk per lot = 1002.50
- baseline risk = 0.10 * 1002.50 = 100.25
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from core.domain.enums import (
    AssetClass,
    OrderType,
    SignalDirection,
    StrategyState,
)
from core.schemas.base import Provenance
from engines.risk import evaluate_proposal

from factories import (
    make_account_state,
    make_instrument,
    make_market_snapshot,
    make_portfolio_state,
    make_risk_policy,
    make_strategy_configuration,
    make_trade_proposal,
)

#: Monday 10:00 UTC — inside any default session, valid trading day.
T0 = datetime(2026, 1, 5, 10, 0, 0, tzinfo=UTC)

#: Baseline quote: bid 1.08000 / ask 1.08005 → mid 1.080025.
BID = Decimal("1.08000")
ASK = Decimal("1.08005")
MID = (BID + ASK) / 2

#: Baseline stop distance (entry - stop).
STOP = Decimal("1.07000")
STOP_DISTANCE = MID - STOP

CONTRACT_SIZE = Decimal("100000")
NOTIONAL_PER_LOT = CONTRACT_SIZE * MID  # 108002.50
RISK_PER_LOT = CONTRACT_SIZE * STOP_DISTANCE  # 1002.50
BASELINE_RISK = Decimal("0.10") * RISK_PER_LOT  # 100.25
LOT_STEP = Decimal("0.01")


def _merge(base: dict[str, Any], overrides: dict[str, Any] | None) -> dict[str, Any]:
    return {**base} if not overrides else {**base, **overrides}


def build_instrument(t: datetime = T0, **overrides: Any):
    base: dict[str, Any] = {
        "instrument_id": "EURUSD",
        "symbol": "EURUSD",
        "exchange": "FX",
        "asset_class": AssetClass.FX,
        "base_currency": "EUR",
        "quote_currency": "USD",
        "price_precision": 5,
        "tick_size": Decimal("0.00001"),
        "lot_size": Decimal("100000"),
        "lot_step": Decimal("0.01"),
        "min_lot": Decimal("0.01"),
        "max_lot": Decimal("100"),
        "contract_size": CONTRACT_SIZE,
    }
    return make_instrument(t, **_merge(base, overrides))


def build_snapshot(t: datetime = T0, **overrides: Any):
    base: dict[str, Any] = {
        "instrument_id": "EURUSD",
        "as_of": t,
        "source_timestamp": t,
        "bid": BID,
        "ask": ASK,
    }
    return make_market_snapshot(t, **_merge(base, overrides))


def build_proposal(t: datetime = T0, **overrides: Any):
    base: dict[str, Any] = {
        "instrument_id": "EURUSD",
        "strategy_id": "strategy-01",
        "strategy_version": "3.1.0",
        "direction": SignalDirection.LONG,
        "order_type": OrderType.MARKET,
        "quantity": Decimal("0.10"),
        "stop_loss": STOP,
        "take_profit": Decimal("1.10000"),
    }
    return make_trade_proposal(t, **_merge(base, overrides))


def build_policy(t: datetime = T0, **overrides: Any):
    base: dict[str, Any] = {
        "policy_id": "risk-17",
        "policy_version": "17.0.0",
        "max_risk_per_trade": Decimal("500"),
        "max_total_exposure": Decimal("5000000"),
        "max_instrument_exposure": Decimal("1000000"),
        "max_asset_class_exposure": {AssetClass.FX: Decimal("5000000")},
        "max_currency_exposure": {
            "EUR": Decimal("5000000"),
            "USD": Decimal("5000000"),
        },
        "max_leverage": Decimal("10"),
        "margin_rates": {AssetClass.FX: Decimal("0.05")},
        "max_positions": 5,
        "max_pending_orders": 5,
        "max_daily_loss": Decimal("1000"),
        "max_drawdown_pct": Decimal("0.2"),
        "max_consecutive_losses": 3,
        "cooldown_seconds": 300,
        "max_spread_relative": Decimal("0.001"),
        "max_slippage_relative": Decimal("0.001"),
        "min_stop_distance": Decimal("0.0010"),
        "market_data_max_age_seconds": 60,
        "heartbeat_max_age_seconds": 60,
    }
    return make_risk_policy(t, **_merge(base, overrides))


def build_account(t: datetime = T0, **overrides: Any):
    base: dict[str, Any] = {
        "account_id": "acc-1",
        "currency": "USD",
        "balance": Decimal("100000"),
        "equity": Decimal("100000"),
        "free_margin": Decimal("90000"),
        "leverage": Decimal("30"),
        "peak_equity": Decimal("110000"),
        "daily_pnl": Decimal("50"),
        "consecutive_losses": 0,
        "broker_connected": True,
        "last_heartbeat_at": t,
        "as_of": t,
    }
    return make_account_state(t, **_merge(base, overrides))


def build_portfolio(t: datetime = T0, **overrides: Any):
    base: dict[str, Any] = {
        "account_id": "acc-1",
        "positions": [],
        "pending_order_count": 0,
        "as_of": t,
    }
    return make_portfolio_state(t, **_merge(base, overrides))


def build_strategy(t: datetime = T0, **overrides: Any):
    base: dict[str, Any] = {
        "strategy_id": "strategy-01",
        "strategy_version": "3.1.0",
        "enabled": True,
        "state": StrategyState.PAPER,
        "as_of": t,
    }
    return make_strategy_configuration(t, **_merge(base, overrides))


def evaluate(
    *,
    proposal: dict[str, Any] | None = None,
    account: dict[str, Any] | None = None,
    portfolio: dict[str, Any] | None = None,
    portfolio_obj: Any | None = None,
    snapshot: dict[str, Any] | None = None,
    strategy: dict[str, Any] | None = None,
    policy: dict[str, Any] | None = None,
    instrument: dict[str, Any] | None = None,
    t: datetime = T0,
):
    """Evaluate a proposal against the baseline inputs with dict overrides.

    ``snapshot={}`` requests a missing snapshot; ``portfolio_obj`` passes a
    pre-built ``PortfolioState`` instead of dict overrides.
    """
    return evaluate_proposal(
        proposal=build_proposal(t, **(proposal or {})),
        account=build_account(t, **(account or {})),
        portfolio=(
            portfolio_obj if portfolio_obj is not None else build_portfolio(t, **(portfolio or {}))
        ),
        snapshot=None if snapshot == {} else build_snapshot(t, **(snapshot or {})),
        strategy=build_strategy(t, **(strategy or {})),
        policy=build_policy(t, **(policy or {})),
        instrument=build_instrument(t, **(instrument or {})),
    )


def provenance_for(t: datetime) -> Provenance:
    return Provenance(producer="tests.risk_helpers", produced_at=t)


def make_position(
    t: datetime,
    position_id: str,
    instrument_id: str,
    side: str,
    quantity: Decimal,
    entry: Decimal,
) -> Any:
    from core.domain.enums import PositionSide
    from core.schemas.trading import PositionSnapshot

    return PositionSnapshot(
        position_id=position_id,
        account_id="acc-1",
        strategy_id="strategy-01",
        instrument_id=instrument_id,
        side=PositionSide(side),
        quantity=quantity,
        average_entry_price=entry,
        as_of=t,
        produced_at=t,
        provenance=provenance_for(t),
    )


def build_portfolio_with_exposure(
    t: datetime,
    *,
    positions: list[Any] | None = None,
    pending_order_count: int = 0,
    total_notional: Decimal | None = None,
    by_instrument: dict[str, Decimal] | None = None,
    by_asset_class: dict[AssetClass, Decimal] | None = None,
    net_by_currency: dict[str, Decimal] | None = None,
):
    from core.schemas.risk import PortfolioExposure

    positions = positions or []
    by_instrument = dict(by_instrument or {})
    exposure = PortfolioExposure(
        total_notional=(sum(by_instrument.values()) if total_notional is None else total_notional),
        by_instrument=by_instrument,
        by_asset_class=dict(by_asset_class or {}),
        net_by_currency=dict(net_by_currency or {}),
    )
    return make_portfolio_state(
        t,
        positions=positions,
        pending_order_count=pending_order_count,
        exposure=exposure,
    )


def new_id() -> str:
    return str(uuid4())


def seconds_after(t: datetime, seconds: int) -> datetime:
    return t + timedelta(seconds=seconds)
