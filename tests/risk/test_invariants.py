"""Critical invariants of the Risk Engine (DoD: no tested path bypasses limits).

- approved risk <= policy risk (per-trade budget)
- approved quantity <= configured maximum
- daily loss breach → no new positions
- stale market data → reject
- disabled strategy → reject
- every soft limit is enforced exactly (no-bypass grid)
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import ClassVar

import pytest
from core.domain.enums import RiskDecisionType, RiskReasonCode, StrategyState

from risk_helpers import (
    CONTRACT_SIZE,
    MID,
    NOTIONAL_PER_LOT,
    RISK_PER_LOT,
    STOP,
    T0,
    evaluate,
)

APPROVE = RiskDecisionType.APPROVE
RESIZE = RiskDecisionType.RESIZE
REJECT = RiskDecisionType.REJECT


def _effective_budget(policy_overrides: dict) -> Decimal:
    budgets = policy_overrides.get("strategy_risk_budgets") or {}
    return min(
        policy_overrides.get("max_risk_per_trade", Decimal("500")),
        budgets.get("strategy-01", Decimal("500")),
    )


class TestApprovedRiskInvariant:
    """approved risk <= policy risk — for every decision type, exactly."""

    SCENARIOS: ClassVar[list[dict]] = [
        {},
        {"proposal": {"quantity": Decimal("1.00")}},
        {"proposal": {"quantity": Decimal("100")}},
        {
            "proposal": {"quantity": Decimal("1.00")},
            "policy": {"strategy_risk_budgets": {"strategy-01": Decimal("77.77")}},
        },
        {
            "proposal": {"quantity": Decimal("0.33")},
            "policy": {"max_risk_per_trade": Decimal("123.45")},
        },
        {"proposal": {"quantity": Decimal("0.105")}},
    ]

    @pytest.mark.parametrize("overrides", SCENARIOS)
    def test_approved_risk_never_exceeds_effective_budget(self, overrides: dict) -> None:
        decision = evaluate(**overrides)
        budget = _effective_budget(overrides.get("policy") or {})
        if decision.decision in (APPROVE, RESIZE):
            assert decision.risk_amount is not None
            assert decision.risk_amount <= budget
            # and the engine-derived quantity stays consistent with the risk math
            expected = decision.approved_quantity * RISK_PER_LOT
            assert decision.risk_amount == expected
        else:
            assert decision.approved_quantity is None
            assert decision.risk_amount is None

    def test_proposed_risk_above_budget_never_approves_as_proposed(self) -> None:
        # 1.00 lot → risk 1002.50 > 500 → APPROVE is impossible at that size.
        decision = evaluate(proposal={"quantity": Decimal("1.00")})
        assert decision.decision is not APPROVE
        if decision.decision is RESIZE:
            assert decision.approved_quantity < Decimal("1.00")
            assert decision.risk_amount <= Decimal("500")


class TestApprovedQuantityInvariant:
    """approved quantity <= configured maximum (policy and instrument)."""

    def test_quantity_never_exceeds_policy_max(self) -> None:
        for policy_max in ("0.05", "0.37", "1.00"):
            decision = evaluate(
                proposal={"quantity": Decimal("100")},
                policy={"max_position_size": Decimal(policy_max)},
            )
            if decision.decision in (APPROVE, RESIZE):
                assert decision.approved_quantity <= Decimal(policy_max)

    def test_quantity_never_exceeds_instrument_max(self) -> None:
        for instrument_max in ("0.05", "0.37", "1.00"):
            decision = evaluate(
                proposal={"quantity": Decimal("100")},
                instrument={"max_lot": Decimal(instrument_max)},
            )
            if decision.decision in (APPROVE, RESIZE):
                assert decision.approved_quantity <= Decimal(instrument_max)

    def test_llm_sized_100_lots_cannot_pass_through(self) -> None:
        decision = evaluate(proposal={"quantity": Decimal("100"), "stop_loss": Decimal("1.07000")})
        assert decision.decision is not APPROVE
        if decision.decision is RESIZE:
            assert decision.approved_quantity < Decimal("100")
            assert decision.risk_amount <= Decimal("500")


class TestBlockingInvariants:
    """The three blocking invariants: daily loss, stale data, disabled strategy."""

    def test_daily_loss_breach_blocks_all_new_positions(self) -> None:
        for quantity in ("0.01", "0.10", "1.00", "50.00"):
            decision = evaluate(
                account={"daily_pnl": Decimal("-1000.01")},
                proposal={"quantity": Decimal(quantity)},
            )
            assert decision.decision is REJECT
            assert RiskReasonCode.MAX_DAILY_LOSS_REACHED in decision.reason_codes
            assert decision.approved_quantity is None

    def test_stale_market_data_always_rejects(self) -> None:
        for age in (61, 120, 3600):
            decision = evaluate(
                snapshot={"source_timestamp": T0 - timedelta(seconds=age)},
                proposal={"quantity": Decimal("0.01")},
            )
            assert decision.decision is REJECT
            assert RiskReasonCode.STALE_QUOTES in decision.reason_codes
            assert decision.approved_quantity is None

    def test_missing_market_data_rejects(self) -> None:
        decision = evaluate(snapshot={})
        assert decision.decision is REJECT
        assert RiskReasonCode.STALE_QUOTES in decision.reason_codes

    def test_disabled_strategy_always_rejects(self) -> None:
        for state, enabled in (
            (StrategyState.PAPER, False),
            (StrategyState.RETIRED, True),
            (StrategyState.CANDIDATE, True),
        ):
            decision = evaluate(strategy={"state": state, "enabled": enabled})
            assert decision.decision is REJECT
            assert RiskReasonCode.STRATEGY_INACTIVE in decision.reason_codes
            assert decision.approved_quantity is None


class TestNoBypassGrid:
    """For each soft limit: an adversarial proposal never bypasses the limit.

    Every assertion recomputes the limit with exact arithmetic — the same
    guarantee the engine itself enforces.
    """

    def test_risk_limit_no_bypass(self) -> None:
        for budget in ("1", "100.25", "500", "99999.99"):
            decision = evaluate(
                proposal={"quantity": Decimal("100")},
                policy={"max_risk_per_trade": Decimal(budget)},
            )
            if decision.decision in (APPROVE, RESIZE):
                assert decision.risk_amount <= Decimal(budget)

    def test_total_exposure_no_bypass(self) -> None:
        for limit in ("1", "9720.225", "108002.50", "5000000"):
            decision = evaluate(
                proposal={"quantity": Decimal("100")},
                policy={"max_total_exposure": Decimal(limit)},
            )
            if decision.decision in (APPROVE, RESIZE):
                assert decision.approved_quantity * NOTIONAL_PER_LOT <= Decimal(limit)

    def test_leverage_no_bypass(self) -> None:
        for max_leverage in ("0.1", "1", "10", "100"):
            decision = evaluate(
                proposal={"quantity": Decimal("100")},
                policy={"max_leverage": Decimal(max_leverage)},
            )
            if decision.decision in (APPROVE, RESIZE):
                assert decision.approved_quantity * NOTIONAL_PER_LOT <= Decimal(
                    max_leverage
                ) * Decimal("100000")

    def test_margin_no_bypass(self) -> None:
        for free_margin in ("1", "540.0125", "54001.25", "90000"):
            decision = evaluate(
                proposal={"quantity": Decimal("100")},
                account={"free_margin": Decimal(free_margin)},
            )
            if decision.decision in (APPROVE, RESIZE):
                required = decision.approved_quantity * NOTIONAL_PER_LOT * Decimal("0.05")
                assert required <= Decimal(free_margin)

    def test_currency_exposure_no_bypass(self) -> None:
        for limit in ("1", "10800.25", "100000"):
            decision = evaluate(
                proposal={"quantity": Decimal("100")},
                policy={
                    "max_currency_exposure": {
                        "EUR": Decimal(limit),
                        "USD": Decimal("100000000"),
                    }
                },
            )
            if decision.decision in (APPROVE, RESIZE):
                added = decision.approved_quantity * NOTIONAL_PER_LOT
                assert added <= Decimal(limit)  # net EUR = 0 → |0 + added| <= limit

    def test_approved_stop_never_trusted_unvalidated(self) -> None:
        decision = evaluate(
            proposal={"quantity": Decimal("1.00"), "stop_loss": STOP + Decimal("0.0000001")}
        )
        # stop distance 0.0100249 < min 0.0010? No — it is >=. This one approves/resizes.
        if decision.decision in (APPROVE, RESIZE):
            assert decision.approved_stop == STOP + Decimal("0.0000001")
            expected_risk = (
                decision.approved_quantity
                * CONTRACT_SIZE
                * abs(MID - (STOP + Decimal("0.0000001")))
            )
            assert decision.risk_amount == expected_risk


class TestDecisionShape:
    def test_reject_never_carries_approved_values(self) -> None:
        decision = evaluate(account={"safe_mode": True})
        assert decision.decision is REJECT
        assert decision.approved_quantity is None
        assert decision.approved_stop is None
        assert decision.risk_amount is None

    def test_approve_never_carries_reason_codes(self) -> None:
        decision = evaluate()
        assert decision.decision is APPROVE
        assert decision.reason_codes == []

    def test_resize_carries_both(self) -> None:
        decision = evaluate(proposal={"quantity": Decimal("1.00")})
        assert decision.decision is RESIZE
        assert decision.approved_quantity is not None
        assert decision.reason_codes

    def test_reason_codes_are_unique_and_ordered(self) -> None:
        decision = evaluate(
            account={
                "safe_mode": True,
                "broker_connected": False,
                "daily_pnl": Decimal("-5000"),
            }
        )
        codes = decision.reason_codes
        assert len(codes) == len(set(codes))
        hard_order = [
            RiskReasonCode.STRATEGY_INACTIVE,
            RiskReasonCode.SYMBOL_NOT_WHITELISTED,
            RiskReasonCode.STALE_QUOTES,
            RiskReasonCode.BROKER_DISCONNECTED,
            RiskReasonCode.HEARTBEAT_LOST,
            RiskReasonCode.SAFE_MODE_ACTIVE,
            RiskReasonCode.TRADING_HOURS_RESTRICTED,
            RiskReasonCode.MAX_DAILY_LOSS_REACHED,
            RiskReasonCode.MAX_DRAWDOWN_REACHED,
            RiskReasonCode.LOSS_SEQUENCE_COOLDOWN,
            RiskReasonCode.MAX_POSITIONS_REACHED,
            RiskReasonCode.MAX_ORDERS_REACHED,
            RiskReasonCode.SPREAD_TOO_HIGH,
            RiskReasonCode.SLIPPAGE_CAP_EXCEEDED,
            RiskReasonCode.INVALID_STOP_DISTANCE,
        ]
        assert codes == [code for code in hard_order if code in codes]
