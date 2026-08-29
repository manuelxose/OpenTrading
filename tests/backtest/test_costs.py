"""Cost-model tests: commission, spread, slippage are real and applied (skill:
trading-cost-validation). Backtests must never be cost-free."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal

from adapters.nautilus.engine import NautilusBacktestRunner
from core.domain.enums import ExecutionState

from conftest import make_config


def _fills(result):
    return [r for r in result.execution_reports if r.status is ExecutionState.FILLED]


def test_commission_is_applied_per_fill(run_result) -> None:
    fills = _fills(run_result)
    assert fills, "the baseline must trade on this dataset"
    assert all(r.commission > 0 for r in fills)
    # 1 bps of notional, floored at 0: commission ≈ qty * px * 1e-4. Nautilus
    # prices the notional on the instrument's rounded fill price, hence 0.01 tolerance.
    for r in fills:
        expected = r.filled_quantity * r.average_fill_price * Decimal("0.0001")
        assert abs(r.commission - expected) < Decimal("0.01")
    assert run_result.metrics.total_commission > 0
    assert sum((r.commission for r in fills), Decimal("0")) == run_result.metrics.total_commission


def test_zero_cost_run_has_zero_commissions() -> None:
    config = make_config(commission={"rate_bps": Decimal("0"), "min_amount": Decimal("0")})
    result = NautilusBacktestRunner(config).run()
    assert result.metrics.total_commission == 0
    assert all(r.commission == 0 for r in _fills(result))


def test_slippage_applied_and_tracked() -> None:
    config = make_config(slippage={"fixed_ticks": 2, "random_min_ticks": 0, "random_max_ticks": 0})
    result = NautilusBacktestRunner(config).run()
    fills = _fills(result)
    assert fills
    tick = config.instrument.tick_size
    # Market buys fill at ask + 2 ticks; sells at bid - 2 ticks. Since the venue's
    # quotes come from the same bar, every fill must be exactly 2 ticks worse than
    # the theoretical quote — the ledger records the difference as slippage.
    expected_total = sum((r.filled_quantity * 2 * tick for r in fills), Decimal("0"))
    assert abs(result.metrics.total_slippage - expected_total) < Decimal("0.001")
    assert result.metrics.total_slippage > 0


def test_zero_slippage_fills_at_the_touch() -> None:
    config = make_config(slippage={"fixed_ticks": 0, "random_min_ticks": 0, "random_max_ticks": 0})
    result = NautilusBacktestRunner(config).run()
    assert result.metrics.total_slippage == 0
    assert all(r.average_fill_price > 0 for r in _fills(result))


def test_spread_config_changes_fill_prices() -> None:
    narrow = make_config(spread={"half_spread_ticks": 1})
    wide = make_config(spread={"half_spread_ticks": 5})
    r1 = NautilusBacktestRunner(narrow).run()
    r2 = NautilusBacktestRunner(wide).run()
    # Wider spread ⇒ strictly worse economics on the same dataset (same seed).
    assert r2.metrics.net_profit < r1.metrics.net_profit
    assert r2.output_hash != r1.output_hash


def test_every_fill_is_reported(run_result) -> None:
    statuses = Counter(r.status.value for r in run_result.execution_reports)
    expected_fills = 2 * run_result.metrics.n_trades + len(run_result.final_positions)
    assert statuses["FILLED"] == expected_fills
    # Every order that reached the venue produced exactly one SUBMITTED report;
    # the rest is FILLED or REJECTED (no silent orders).
    assert statuses["SUBMITTED"] == statuses["FILLED"] + statuses.get("REJECTED", 0)


def test_partial_fill_status_never_claimed_for_single_fill_orders(run_result) -> None:
    assert all(r.status is not ExecutionState.PARTIAL_FILL for r in run_result.execution_reports)
