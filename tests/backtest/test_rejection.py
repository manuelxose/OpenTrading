"""Order rejection simulation: deterministic rules + engine-native rejections."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from adapters.nautilus.engine import NautilusBacktestRunner
from adapters.nautilus.rejection import (
    LOT_STEP_INVALID,
    MARKET_CLOSED,
    PRICE_OUTSIDE_MARKET,
    SIMULATED_REJECTION,
    SIZE_ABOVE_MAXIMUM,
    SIZE_BELOW_MINIMUM,
    OrderRejectionSim,
)
from core.domain.enums import ExecutionState, OrderSide, OrderType

from conftest import make_config
from factories import FIXED_START, make_order_intent


def _sim(**overrides):
    config = make_config(
        rejection=overrides.get("rejection", {}),
        **{k: v for k, v in overrides.items() if k != "rejection"},
    )
    return OrderRejectionSim(config.rejection, config.seed, config.instrument)


def test_lot_rules_reject_out_of_range() -> None:
    sim = _sim()
    now = FIXED_START + timedelta(minutes=30)
    below = make_order_intent(FIXED_START, quantity=Decimal("500"))  # < min 1000 units
    assert sim.reason(below, now, Decimal("1.08000"), Decimal("1.08005")) == SIZE_BELOW_MINIMUM
    above = make_order_intent(FIXED_START, quantity=Decimal("20000000"))  # > max 10M
    assert sim.reason(above, now, Decimal("1.08000"), Decimal("1.08005")) == SIZE_ABOVE_MAXIMUM
    bad_step = make_order_intent(FIXED_START, quantity=Decimal("1500"))  # not a lot step
    assert sim.reason(bad_step, now, Decimal("1.08000"), Decimal("1.08005")) == LOT_STEP_INVALID


def test_price_guard_rejects_crossed_limits() -> None:
    sim = _sim()
    now = FIXED_START + timedelta(minutes=30)
    bid = Decimal("1.08000")
    ask = Decimal("1.08005")
    buy_above = make_order_intent(
        FIXED_START,
        order_type=OrderType.LIMIT,
        side=OrderSide.BUY,
        price=Decimal("1.08010"),
        quantity=Decimal("100000"),
    )
    assert sim.reason(buy_above, now, bid, ask) == PRICE_OUTSIDE_MARKET
    ok_buy = make_order_intent(
        FIXED_START,
        order_type=OrderType.LIMIT,
        side=OrderSide.BUY,
        price=Decimal("1.07900"),
        quantity=Decimal("100000"),
    )
    assert sim.reason(ok_buy, now, bid, ask) is None


def test_market_hours_rejection() -> None:
    sim = _sim()
    sim.set_session(FIXED_START, FIXED_START + timedelta(hours=8))
    before = make_order_intent(FIXED_START, quantity=Decimal("100000"))
    assert sim.reason(before, FIXED_START - timedelta(seconds=1), None, None) == MARKET_CLOSED
    during = make_order_intent(FIXED_START, quantity=Decimal("100000"))
    assert sim.reason(during, FIXED_START + timedelta(hours=1), None, None) is None


def test_random_rejection_is_seeded_and_reproducible() -> None:
    now = FIXED_START + timedelta(minutes=30)
    sim_a = _sim(
        rejection={
            "probability": 0.5,
            "enforce_lot_rules": False,
            "enforce_price_guard": False,
            "enforce_market_hours": False,
        }
    )
    sim_b = _sim(
        rejection={
            "probability": 0.5,
            "enforce_lot_rules": False,
            "enforce_price_guard": False,
            "enforce_market_hours": False,
        }
    )
    intent = make_order_intent(FIXED_START, quantity=Decimal("100000"))
    outcomes_a = [sim_a.reason(intent, now, None, None) for _ in range(100)]
    outcomes_b = [sim_b.reason(intent, now, None, None) for _ in range(100)]
    assert outcomes_a == outcomes_b
    assert any(o == SIMULATED_REJECTION for o in outcomes_a)
    assert any(o is None for o in outcomes_a)


def test_full_rejection_probability_blocks_all_orders() -> None:
    config = make_config(rejection={"probability": 1.0})
    result = NautilusBacktestRunner(config).run()
    assert result.metrics.n_trades == 0
    assert all(r.status is ExecutionState.REJECTED for r in result.execution_reports)
    assert all(r.reject_reason == SIMULATED_REJECTION for r in result.execution_reports)


def test_engine_rejects_stop_order_on_wrong_side() -> None:
    """A STOP BUY whose trigger rests below the market is rejected by the venue
    itself (reject_stop_orders=True) and surfaces as a REJECTED report."""
    config = make_config()

    class StopIntentStrategy:
        strategy_id = "scripted-stop"
        strategy_version = "1.0.0"

        def __init__(self) -> None:
            self._bars_seen = 0

        def on_bar(self, ctx):
            self._bars_seen += 1
            # Wait until a quote exists (2nd bar), then send a stop buy whose
            # trigger rests below the ask — the venue must reject it.
            if self._bars_seen != 2 or ctx.last_ask is None:
                return []
            intent = make_order_intent(
                FIXED_START,
                order_type=OrderType.STOP,
                side=OrderSide.BUY,
                price=ctx.last_ask - Decimal("0.00100"),
                quantity=Decimal("100000"),
                operating_mode="BACKTEST",
            )
            return [intent]

    result = NautilusBacktestRunner(config).run(StopIntentStrategy())
    rejected = [r for r in result.execution_reports if r.status is ExecutionState.REJECTED]
    assert rejected, "the venue must reject a stop order on the wrong side of the market"
    assert all(r.reject_reason for r in rejected)
