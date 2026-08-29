"""Boundary tests: exactly-at-limit behavior with exact Decimal arithmetic.

Constants: notional per lot = 108002.50, risk per lot = 1002.50,
baseline proposal = 0.10 lots → notional 10800.25, risk 100.25.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from core.domain.enums import RiskDecisionType, RiskReasonCode

from risk_helpers import (
    ASK,
    BID,
    MID,
    NOTIONAL_PER_LOT,
    RISK_PER_LOT,
    STOP,
    STOP_DISTANCE,
    T0,
    build_portfolio,
    evaluate,
    make_position,
)

APPROVE = RiskDecisionType.APPROVE
RESIZE = RiskDecisionType.RESIZE
REJECT = RiskDecisionType.REJECT

#: Exact notional of the baseline 0.10-lot proposal.
BASELINE_NOTIONAL = Decimal("0.10") * NOTIONAL_PER_LOT  # 10800.25
#: Exact risk of the baseline proposal.
BASELINE_RISK = Decimal("0.10") * RISK_PER_LOT  # 100.25


class TestRiskBoundary:
    def test_risk_exactly_at_budget_approves(self) -> None:
        decision = evaluate(policy={"max_risk_per_trade": BASELINE_RISK})
        assert decision.decision is APPROVE

    def test_risk_one_unit_above_budget_resizes(self) -> None:
        decision = evaluate(policy={"max_risk_per_trade": BASELINE_RISK - Decimal("0.001")})
        assert decision.decision is RESIZE
        assert RiskReasonCode.RISK_LIMIT_EXCEEDED in decision.reason_codes
        assert decision.risk_amount <= BASELINE_RISK - Decimal("0.001")


class TestExposureBoundary:
    def test_total_exposure_exactly_at_limit_approves(self) -> None:
        decision = evaluate(policy={"max_total_exposure": BASELINE_NOTIONAL})
        assert decision.decision is APPROVE

    def test_total_exposure_one_unit_above_limit_resizes(self) -> None:
        decision = evaluate(policy={"max_total_exposure": BASELINE_NOTIONAL - Decimal("0.01")})
        assert decision.decision is RESIZE
        assert RiskReasonCode.EXPOSURE_LIMIT_EXCEEDED in decision.reason_codes

    def test_instrument_exposure_exactly_at_limit_approves(self) -> None:
        decision = evaluate(policy={"max_instrument_exposure": BASELINE_NOTIONAL})
        assert decision.decision is APPROVE

    def test_currency_exposure_exactly_at_limit_approves(self) -> None:
        decision = evaluate(
            policy={"max_currency_exposure": {"EUR": BASELINE_NOTIONAL, "USD": Decimal("5000000")}}
        )
        assert decision.decision is APPROVE

    def test_currency_exposure_one_unit_above_limit_resizes(self) -> None:
        decision = evaluate(
            policy={
                "max_currency_exposure": {
                    "EUR": BASELINE_NOTIONAL - Decimal("0.01"),
                    "USD": Decimal("5000000"),
                }
            }
        )
        assert decision.decision is RESIZE
        assert RiskReasonCode.CONCENTRATION_LIMIT_EXCEEDED in decision.reason_codes


class TestLeverageMarginBoundary:
    def test_leverage_exactly_at_limit_approves(self) -> None:
        max_leverage = BASELINE_NOTIONAL / Decimal("100000")  # 0.1080025
        decision = evaluate(policy={"max_leverage": max_leverage})
        assert decision.decision is APPROVE

    def test_leverage_one_unit_above_limit_resizes(self) -> None:
        max_leverage = (BASELINE_NOTIONAL - Decimal("0.01")) / Decimal("100000")
        decision = evaluate(policy={"max_leverage": max_leverage})
        assert decision.decision is RESIZE
        assert RiskReasonCode.LEVERAGE_LIMIT_EXCEEDED in decision.reason_codes

    def test_margin_exactly_enough_approves(self) -> None:
        free_margin = BASELINE_NOTIONAL * Decimal("0.05")
        decision = evaluate(account={"free_margin": free_margin})
        assert decision.decision is APPROVE

    def test_margin_one_unit_short_resizes(self) -> None:
        free_margin = BASELINE_NOTIONAL * Decimal("0.05") - Decimal("0.01")
        decision = evaluate(account={"free_margin": free_margin})
        assert decision.decision is RESIZE
        assert RiskReasonCode.INSUFFICIENT_MARGIN in decision.reason_codes


class TestLossBoundaries:
    def test_daily_loss_exactly_at_limit_rejects(self) -> None:
        decision = evaluate(account={"daily_pnl": Decimal("-1000")})
        assert decision.decision is REJECT
        assert RiskReasonCode.MAX_DAILY_LOSS_REACHED in decision.reason_codes

    def test_daily_loss_just_below_limit_approves(self) -> None:
        decision = evaluate(account={"daily_pnl": Decimal("-999.999")})
        assert decision.decision is APPROVE

    def test_drawdown_exactly_at_limit_rejects(self) -> None:
        decision = evaluate(account={"equity": Decimal("80000"), "peak_equity": Decimal("100000")})
        assert decision.decision is REJECT
        assert RiskReasonCode.MAX_DRAWDOWN_REACHED in decision.reason_codes

    def test_drawdown_just_below_limit_approves(self) -> None:
        decision = evaluate(
            account={"equity": Decimal("80000"), "peak_equity": Decimal("100000")},
            policy={"max_drawdown_pct": Decimal("0.200001")},
        )
        assert decision.decision is APPROVE

    def test_cooldown_exactly_elapsed_approves(self) -> None:
        decision = evaluate(
            account={
                "consecutive_losses": 3,
                "last_loss_at": T0 - timedelta(seconds=300),
            }
        )
        assert decision.decision is APPROVE

    def test_cooldown_one_second_left_rejects(self) -> None:
        decision = evaluate(
            account={
                "consecutive_losses": 3,
                "last_loss_at": T0 - timedelta(seconds=299),
            }
        )
        assert decision.decision is REJECT
        assert RiskReasonCode.LOSS_SEQUENCE_COOLDOWN in decision.reason_codes


class TestMarketQualityBoundaries:
    def test_spread_exactly_at_limit_approves(self) -> None:
        relative_spread = (ASK - BID) / MID
        decision = evaluate(policy={"max_spread_relative": relative_spread})
        assert decision.decision is APPROVE

    def test_spread_one_epsilon_above_limit_rejects(self) -> None:
        relative_spread = (ASK - BID) / MID
        decision = evaluate(policy={"max_spread_relative": relative_spread - Decimal("1E-9")})
        assert decision.decision is REJECT
        assert RiskReasonCode.SPREAD_TOO_HIGH in decision.reason_codes

    def test_slippage_exactly_at_limit_approves(self) -> None:
        relative_slippage = (ASK - MID) / MID
        decision = evaluate(policy={"max_slippage_relative": relative_slippage})
        assert decision.decision is APPROVE

    def test_slippage_one_epsilon_above_limit_rejects(self) -> None:
        relative_slippage = (ASK - MID) / MID
        decision = evaluate(
            policy={
                "max_spread_relative": Decimal("0.002"),  # spread itself stays OK
                "max_slippage_relative": relative_slippage - Decimal("1E-9"),
            }
        )
        assert decision.decision is REJECT
        assert RiskReasonCode.SLIPPAGE_CAP_EXCEEDED in decision.reason_codes

    def test_market_data_exactly_max_age_approves(self) -> None:
        decision = evaluate(snapshot={"source_timestamp": T0 - timedelta(seconds=60)})
        assert decision.decision is APPROVE

    def test_market_data_one_second_over_max_age_rejects(self) -> None:
        decision = evaluate(snapshot={"source_timestamp": T0 - timedelta(seconds=61)})
        assert decision.decision is REJECT
        assert RiskReasonCode.STALE_QUOTES in decision.reason_codes


class TestStopDistanceBoundaries:
    def test_stop_exactly_min_distance_approves(self) -> None:
        decision = evaluate(policy={"min_stop_distance": STOP_DISTANCE})
        assert decision.decision is APPROVE

    def test_stop_one_tick_inside_min_distance_rejects(self) -> None:
        decision = evaluate(
            proposal={"stop_loss": STOP + Decimal("0.00001")},  # closer by one tick
            policy={"min_stop_distance": STOP_DISTANCE},
        )
        assert decision.decision is REJECT
        assert RiskReasonCode.INVALID_STOP_DISTANCE in decision.reason_codes

    def test_stop_exactly_at_entry_rejects(self) -> None:
        decision = evaluate(proposal={"stop_loss": MID})
        assert decision.decision is REJECT
        assert RiskReasonCode.INVALID_STOP_DISTANCE in decision.reason_codes


class TestSizeBoundaries:
    def test_quantity_exactly_at_instrument_max_approves(self) -> None:
        decision = evaluate(
            proposal={"quantity": Decimal("0.10")},
            instrument={"max_lot": Decimal("0.10")},
            policy={
                "max_total_exposure": Decimal("5000000"),
                "max_risk_per_trade": Decimal("5000"),
            },
        )
        assert decision.decision is APPROVE

    def test_quantity_one_step_above_max_resizes(self) -> None:
        decision = evaluate(
            proposal={"quantity": Decimal("0.11")},
            instrument={"max_lot": Decimal("0.10")},
            policy={
                "max_total_exposure": Decimal("5000000"),
                "max_risk_per_trade": Decimal("5000"),
            },
        )
        assert decision.decision is RESIZE
        assert RiskReasonCode.SIZE_ABOVE_MAXIMUM in decision.reason_codes
        assert decision.approved_quantity == Decimal("0.10")

    def test_quantity_exactly_at_minimum_approves(self) -> None:
        decision = evaluate(
            proposal={"quantity": Decimal("0.01")},
            policy={"max_risk_per_trade": Decimal("5000")},
        )
        assert decision.decision is APPROVE


class TestCountBoundaries:
    def test_positions_exactly_at_cap_approves(self) -> None:
        from core.schemas.risk import PortfolioExposure

        portfolio = build_portfolio(
            T0,
            positions=[make_position(T0, "pos-1", "GBPUSD", "LONG", Decimal("1"), Decimal("1.25"))],
            exposure=PortfolioExposure(
                total_notional=Decimal("125000"),
                by_instrument={"GBPUSD": Decimal("125000")},
                by_asset_class={"FX": Decimal("125000")},
            ),
        )
        decision = evaluate(portfolio_obj=portfolio, policy={"max_positions": 2})
        assert decision.decision is APPROVE

    def test_positions_one_over_cap_rejects(self) -> None:
        from core.schemas.risk import PortfolioExposure

        portfolio = build_portfolio(
            T0,
            positions=[make_position(T0, "pos-1", "GBPUSD", "LONG", Decimal("1"), Decimal("1.25"))],
            exposure=PortfolioExposure(
                total_notional=Decimal("125000"),
                by_instrument={"GBPUSD": Decimal("125000")},
                by_asset_class={"FX": Decimal("125000")},
            ),
        )
        decision = evaluate(portfolio_obj=portfolio, policy={"max_positions": 1})
        assert decision.decision is REJECT
        assert RiskReasonCode.MAX_POSITIONS_REACHED in decision.reason_codes

    def test_orders_exactly_at_cap_approves(self) -> None:
        decision = evaluate(
            portfolio={"pending_order_count": 4},
            policy={"max_pending_orders": 5},
        )
        assert decision.decision is APPROVE

    def test_orders_one_over_cap_rejects(self) -> None:
        decision = evaluate(
            portfolio={"pending_order_count": 5},
            policy={"max_pending_orders": 5},
        )
        assert decision.decision is REJECT
        assert RiskReasonCode.MAX_ORDERS_REACHED in decision.reason_codes
