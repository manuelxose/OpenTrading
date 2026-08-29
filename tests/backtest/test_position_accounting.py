"""Position accounting: the domain ledger must agree with the venue (INV-6)."""

from __future__ import annotations

from decimal import Decimal

from adapters.nautilus.engine import NautilusBacktestRunner
from core.domain.enums import ExecutionState, PositionSide, SignalDirection

from conftest import make_config


def test_ledger_balances_match_venue(run_result) -> None:
    """The mirrored cash book equals the venue's own account, per currency."""
    assert run_result.venue_balances is not None
    for currency, balance in run_result.final_balances.items():
        assert run_result.venue_balances[currency] == balance


def test_cash_flow_equals_realized_minus_costs(run_result) -> None:
    """USD cash delta == sum(realized_pnl - costs) - open-position cash outlay."""
    realized = sum((o.realized_pnl - o.costs for o in run_result.trade_outcomes), Decimal("0"))
    open_outlay = sum(
        (snap.quantity * snap.average_entry_price for snap in run_result.final_positions),
        Decimal("0"),
    )
    usd_delta = run_result.final_balances["USD"] - Decimal("1000000")
    assert abs(usd_delta - (realized - open_outlay)) < Decimal("0.001")


def test_trade_outcomes_are_internally_consistent(run_result) -> None:
    assert run_result.trade_outcomes, "expected closed trades on this dataset"
    for outcome in run_result.trade_outcomes:
        assert outcome.direction is SignalDirection.LONG
        assert outcome.quantity == Decimal("100000")
        assert outcome.exit_price > 0
        assert outcome.entry_price > 0
        assert outcome.costs >= 0
        assert outcome.slippage_total is not None and outcome.slippage_total >= 0
        assert outcome.closed_at >= outcome.opened_at
        if outcome.direction is SignalDirection.LONG:
            expected_pnl = (outcome.exit_price - outcome.entry_price) * outcome.quantity
            assert abs(outcome.realized_pnl - expected_pnl) < Decimal("0.001")


def test_positions_are_flat_at_end(run_result) -> None:
    # exit_at_end=True ⇒ the baseline exits its position on the last bar.
    assert run_result.final_positions == []


def test_open_position_when_no_exit_at_end() -> None:
    config = make_config(baseline={"exit_at_end": False})
    result = NautilusBacktestRunner(config).run()
    assert result.final_positions, "without exit_at_end the baseline must remain long"
    for snapshot in result.final_positions:
        assert snapshot.side is PositionSide.LONG
        assert snapshot.quantity > 0
        assert snapshot.average_entry_price > 0


def test_snapshots_carry_mark_and_unrealized() -> None:
    # No exit_at_end ⇒ the run ends with an open position whose snapshot must
    # carry a mark price and unrealized PnL from the quote stream.
    config = make_config(baseline={"exit_at_end": False})
    result = NautilusBacktestRunner(config).run()
    for snapshot in result.final_positions:
        assert snapshot.mark_price is not None
        assert snapshot.unrealized_pnl is not None


def test_no_fills_means_no_positions() -> None:
    config = make_config(rejection={"probability": 1.0})
    result = NautilusBacktestRunner(config).run()
    assert result.final_positions == []
    assert result.trade_outcomes == []
    assert all(r.status is ExecutionState.REJECTED for r in result.execution_reports)
