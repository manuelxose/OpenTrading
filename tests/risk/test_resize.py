"""RESIZE paths: the engine reduces the quantity to the binding soft limit.

The approved quantity is always computed by the engine (INV-1) — the proposal's
quantity is advisory. Constants: notional per lot = 108002.50, risk per lot =
1002.50 (contract_size 100000).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from core.domain.enums import AssetClass, RiskDecisionType, RiskReasonCode
from pydantic import ValidationError

from risk_helpers import (
    NOTIONAL_PER_LOT,
    T0,
    build_policy,
    build_portfolio_with_exposure,
    evaluate,
    make_position,
)

RESIZE = RiskDecisionType.RESIZE
REJECT = RiskDecisionType.REJECT


class TestRiskBudgetResize:
    def test_risk_above_budget_resizes(self) -> None:
        decision = evaluate(proposal={"quantity": Decimal("1.00")})
        assert decision.decision is RESIZE
        assert RiskReasonCode.RISK_LIMIT_EXCEEDED in decision.reason_codes
        assert decision.approved_quantity == Decimal("0.49")  # floor(500 / 1002.5)
        assert decision.risk_amount <= Decimal("500")

    def test_strategy_budget_overrides_global(self) -> None:
        decision = evaluate(
            proposal={"quantity": Decimal("1.00")},
            policy={"strategy_risk_budgets": {"strategy-01": Decimal("100")}},
        )
        assert decision.decision is RESIZE
        assert decision.approved_quantity == Decimal("0.09")  # floor(100 / 1002.5)
        assert decision.risk_amount <= Decimal("100")

    def test_resize_risk_never_exceeds_effective_budget(self) -> None:
        decision = evaluate(
            proposal={"quantity": Decimal("0.33")},
            policy={"max_risk_per_trade": Decimal("123.45")},
        )
        assert decision.decision is RESIZE
        assert decision.risk_amount <= Decimal("123.45")


class TestExposureResize:
    def test_total_exposure_binds(self) -> None:
        remaining = Decimal("0.09") * NOTIONAL_PER_LOT  # 9720.225
        decision = evaluate(
            proposal={"quantity": Decimal("1.00")},
            policy={"max_total_exposure": remaining},
        )
        assert decision.decision is RESIZE
        assert RiskReasonCode.EXPOSURE_LIMIT_EXCEEDED in decision.reason_codes
        assert decision.approved_quantity == Decimal("0.09")

    def test_total_exposure_with_existing_positions(self) -> None:
        remaining = Decimal("0.05") * NOTIONAL_PER_LOT
        decision = evaluate(
            proposal={"quantity": Decimal("1.00")},
            policy={
                "max_total_exposure": remaining + Decimal("100000"),  # existing notional below
            },
            portfolio_obj=_portfolio(total_notional=Decimal("100000")),
        )
        assert decision.decision is RESIZE
        assert decision.approved_quantity == Decimal("0.05")
        # approved notional + existing <= limit
        assert decision.approved_quantity * NOTIONAL_PER_LOT + Decimal("100000") <= (
            remaining + Decimal("100000")
        )

    def test_instrument_exposure_binds(self) -> None:
        remaining = Decimal("0.09") * NOTIONAL_PER_LOT
        decision = evaluate(
            proposal={"quantity": Decimal("1.00")},
            policy={"max_instrument_exposure": remaining + Decimal("1000")},
            portfolio_obj=_portfolio(
                positions=[
                    make_position(T0, "pos-1", "EURUSD", "LONG", Decimal("1"), Decimal("1.08"))
                ],
                total_notional=Decimal("1000"),
                by_instrument={"EURUSD": Decimal("1000")},
            ),
        )
        assert decision.decision is RESIZE
        assert RiskReasonCode.CONCENTRATION_LIMIT_EXCEEDED in decision.reason_codes
        assert decision.approved_quantity == Decimal("0.09")

    def test_asset_class_exposure_binds(self) -> None:
        remaining = Decimal("0.09") * NOTIONAL_PER_LOT
        decision = evaluate(
            proposal={"quantity": Decimal("1.00")},
            policy={"max_asset_class_exposure": {AssetClass.FX: remaining + Decimal("2000")}},
            portfolio_obj=_portfolio(
                total_notional=Decimal("2000"),
                by_asset_class={AssetClass.FX: Decimal("2000")},
            ),
        )
        assert decision.decision is RESIZE
        assert RiskReasonCode.CONCENTRATION_LIMIT_EXCEEDED in decision.reason_codes
        assert decision.approved_quantity == Decimal("0.09")

    def test_currency_exposure_binds(self) -> None:
        remaining = Decimal("0.09") * NOTIONAL_PER_LOT
        decision = evaluate(
            proposal={"quantity": Decimal("1.00")},
            policy={
                "max_currency_exposure": {
                    "EUR": remaining + Decimal("9000"),  # net long EUR 9000 already
                    "USD": Decimal("5000000"),
                }
            },
            portfolio_obj=_portfolio(net_by_currency={"EUR": Decimal("9000")}),
        )
        assert decision.decision is RESIZE
        assert RiskReasonCode.CONCENTRATION_LIMIT_EXCEEDED in decision.reason_codes
        assert decision.approved_quantity == Decimal("0.09")

    def test_exposure_exhausted_rejects(self) -> None:
        # remaining headroom below one lot step → cannot size ≥ minimum → REJECT
        decision = evaluate(
            proposal={"quantity": Decimal("1.00")},
            policy={"max_total_exposure": Decimal("0.01")},
        )
        assert decision.decision is REJECT
        assert RiskReasonCode.EXPOSURE_LIMIT_EXCEEDED in decision.reason_codes
        assert RiskReasonCode.SIZE_BELOW_MINIMUM in decision.reason_codes
        assert decision.approved_quantity is None


class TestLeverageMarginResize:
    def test_leverage_binds(self) -> None:
        allowed = Decimal("0.09") * NOTIONAL_PER_LOT  # 9720.225
        decision = evaluate(
            proposal={"quantity": Decimal("1.00")},
            policy={"max_leverage": allowed / Decimal("100000")},
        )
        assert decision.decision is RESIZE
        assert RiskReasonCode.LEVERAGE_LIMIT_EXCEEDED in decision.reason_codes
        assert decision.approved_quantity == Decimal("0.09")

    def test_margin_binds(self) -> None:
        required = Decimal("0.09") * NOTIONAL_PER_LOT * Decimal("0.05")
        decision = evaluate(
            proposal={"quantity": Decimal("1.00")},
            account={"free_margin": required},
        )
        assert decision.decision is RESIZE
        assert RiskReasonCode.INSUFFICIENT_MARGIN in decision.reason_codes
        assert decision.approved_quantity == Decimal("0.09")

    def test_asset_class_not_admitted_by_policy_rejects(self) -> None:
        # CRYPTO is absent from the policy's exposure/margin tables → limit 0,
        # cap 0 → the proposal cannot size above the minimum → REJECT.
        decision = evaluate(
            proposal={"quantity": Decimal("1.00")},
            instrument={"asset_class": AssetClass.CRYPTO},
        )
        assert decision.decision is REJECT
        assert RiskReasonCode.CONCENTRATION_LIMIT_EXCEEDED in decision.reason_codes
        assert RiskReasonCode.SIZE_BELOW_MINIMUM in decision.reason_codes
        assert decision.approved_quantity is None

    def test_margin_rate_zero_for_class_rejects(self) -> None:
        # Margin rates must be > 0 — the policy contract enforces it.
        with pytest.raises(ValidationError):
            build_policy(
                T0,
                margin_rates={AssetClass.FX: Decimal("0")},
            )


class TestSizeNormalization:
    def test_lot_step_not_multiple_resizes(self) -> None:
        decision = evaluate(proposal={"quantity": Decimal("0.105")})
        assert decision.decision is RESIZE
        assert RiskReasonCode.LOT_STEP_INVALID in decision.reason_codes
        assert decision.approved_quantity == Decimal("0.10")

    def test_above_policy_max_size_resizes(self) -> None:
        decision = evaluate(
            proposal={"quantity": Decimal("1.00")},
            policy={"max_position_size": Decimal("0.05")},
        )
        assert decision.decision is RESIZE
        assert RiskReasonCode.SIZE_ABOVE_MAXIMUM in decision.reason_codes
        assert decision.approved_quantity == Decimal("0.05")

    def test_above_instrument_max_lot_resizes(self) -> None:
        decision = evaluate(
            proposal={"quantity": Decimal("1.00")},
            instrument={"max_lot": Decimal("0.05")},
        )
        assert decision.decision is RESIZE
        assert RiskReasonCode.SIZE_ABOVE_MAXIMUM in decision.reason_codes
        assert decision.approved_quantity == Decimal("0.05")

    def test_below_minimum_rejects(self) -> None:
        decision = evaluate(proposal={"quantity": Decimal("0.005")})
        assert decision.decision is REJECT
        assert RiskReasonCode.SIZE_BELOW_MINIMUM in decision.reason_codes
        assert decision.approved_quantity is None

    def test_below_policy_min_rejects(self) -> None:
        decision = evaluate(
            proposal={"quantity": Decimal("0.05")},
            policy={"min_position_size": Decimal("0.10")},
        )
        assert decision.decision is REJECT
        assert RiskReasonCode.SIZE_BELOW_MINIMUM in decision.reason_codes


class TestResizeShape:
    def test_resize_carries_approved_values_and_codes(self) -> None:
        decision = evaluate(proposal={"quantity": Decimal("1.00")})
        assert decision.approved_quantity is not None
        assert decision.approved_stop is not None
        assert decision.risk_amount is not None
        assert len(decision.reason_codes) >= 1

    def test_resize_never_exceeds_proposal_quantity(self) -> None:
        decision = evaluate(proposal={"quantity": Decimal("100")})
        assert decision.approved_quantity <= Decimal("100")

    def test_resize_quantity_is_lot_step_multiple(self) -> None:
        for quantity in ("0.111", "0.999", "7.777", "0.105"):
            decision = evaluate(proposal={"quantity": Decimal(quantity)})
            if decision.decision in (RESIZE, RiskDecisionType.APPROVE):
                assert decision.approved_quantity % Decimal("0.01") == 0

    def test_resize_quantity_at_least_minimum(self) -> None:
        for quantity in ("0.111", "0.999", "7.777"):
            decision = evaluate(proposal={"quantity": Decimal(quantity)})
            if decision.decision in (RESIZE, RiskDecisionType.APPROVE):
                assert decision.approved_quantity >= Decimal("0.01")

    def test_multiple_binding_codes_reported_in_order(self) -> None:
        decision = evaluate(
            proposal={"quantity": Decimal("100")},
            policy={
                "max_total_exposure": Decimal("200000"),  # ~1.85 lots
                "max_position_size": Decimal("1.00"),  # binds tighter
                "max_risk_per_trade": Decimal("200"),  # ~0.199 lots — tightest
            },
        )
        assert decision.decision is RESIZE
        codes = decision.reason_codes
        assert RiskReasonCode.RISK_LIMIT_EXCEEDED in codes
        assert RiskReasonCode.EXPOSURE_LIMIT_EXCEEDED in codes
        assert RiskReasonCode.SIZE_ABOVE_MAXIMUM in codes
        assert codes == sorted(codes, key=lambda c: _SOFT_ORDER.index(c))


_SOFT_ORDER = [
    RiskReasonCode.RISK_LIMIT_EXCEEDED,
    RiskReasonCode.CONCENTRATION_LIMIT_EXCEEDED,
    RiskReasonCode.EXPOSURE_LIMIT_EXCEEDED,
    RiskReasonCode.LEVERAGE_LIMIT_EXCEEDED,
    RiskReasonCode.INSUFFICIENT_MARGIN,
    RiskReasonCode.SIZE_ABOVE_MAXIMUM,
    RiskReasonCode.LOT_STEP_INVALID,
    RiskReasonCode.SIZE_BELOW_MINIMUM,
]


def _portfolio(
    *,
    positions: list | None = None,
    pending_order_count: int = 0,
    total_notional: Decimal = Decimal("0"),
    by_instrument: dict | None = None,
    by_asset_class: dict | None = None,
    net_by_currency: dict | None = None,
):
    return build_portfolio_with_exposure(
        T0,
        positions=positions or [],
        pending_order_count=pending_order_count,
        total_notional=total_notional,
        by_instrument=by_instrument or {},
        by_asset_class=by_asset_class or {},
        net_by_currency=net_by_currency or {},
    )
