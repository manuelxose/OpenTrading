"""Validation tests for the Risk & Policy contracts and the RESIZE decision shape."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from core.domain.enums import AssetClass, RiskDecisionType, RiskReasonCode
from pydantic import ValidationError

from factories import make_account_state, make_risk_decision_resize, make_risk_policy


class TestRiskPolicy:
    def test_missing_margin_rate_for_exposed_class_rejected(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="margin_rates"):
            make_risk_policy(
                fixed_start,
                max_asset_class_exposure={AssetClass.CRYPTO: Decimal("100000")},
            )

    def test_non_positive_strategy_budget_rejected(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="budget"):
            make_risk_policy(fixed_start, strategy_risk_budgets={"strategy-01": Decimal("0")})

    def test_invalid_currency_code_rejected(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="currency"):
            make_risk_policy(
                fixed_start,
                max_currency_exposure={"eur": Decimal("100000")},
            )

    def test_margin_rate_out_of_range_rejected(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="margin"):
            make_risk_policy(fixed_start, margin_rates={AssetClass.FX: Decimal("1.5")})

    def test_min_size_above_max_rejected(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="min_position_size"):
            make_risk_policy(
                fixed_start,
                min_position_size=Decimal("1"),
                max_position_size=Decimal("0.5"),
            )

    def test_trading_days_out_of_range_rejected(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="trading_days"):
            make_risk_policy(fixed_start, trading_days=frozenset({7}))

    def test_single_session_bound_rejected(self, fixed_start: datetime) -> None:
        from datetime import time

        with pytest.raises(ValidationError, match="session"):
            make_risk_policy(fixed_start, session_open_utc=time(9, 0))

    def test_drawdown_limit_ge_one_rejected(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError):
            make_risk_policy(fixed_start, max_drawdown_pct=Decimal("1"))


class TestAccountState:
    def test_loss_streak_requires_timestamp(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="last_loss_at"):
            make_account_state(fixed_start, consecutive_losses=2, last_loss_at=None)

    def test_non_positive_equity_rejected(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError):
            make_account_state(fixed_start, equity=Decimal("0"))

    def test_valid_state_constructs(self, fixed_start: datetime) -> None:
        state = make_account_state(
            fixed_start,
            consecutive_losses=2,
            last_loss_at=fixed_start - timedelta(minutes=5),
        )
        assert state.consecutive_losses == 2


class TestRiskDecisionResize:
    def test_resize_requires_approved_values(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="approved"):
            make_risk_decision_resize(fixed_start, approved_quantity=None)

    def test_resize_requires_reason_codes(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="reason_code"):
            make_risk_decision_resize(fixed_start, reason_codes=[])

    def test_resize_carries_both_values_and_codes(self, fixed_start: datetime) -> None:
        decision = make_risk_decision_resize(fixed_start)
        assert decision.decision is RiskDecisionType.RESIZE
        assert decision.approved_quantity is not None
        assert decision.approved_stop is not None
        assert decision.risk_amount is not None
        assert decision.reason_codes

    def test_approve_still_forbids_reason_codes(self, fixed_start: datetime) -> None:
        from factories import make_risk_decision_approve

        with pytest.raises(ValidationError, match="reason_codes"):
            make_risk_decision_approve(fixed_start, reason_codes=[RiskReasonCode.STALE_QUOTES])

    def test_reject_still_forbids_approved_values(self, fixed_start: datetime) -> None:
        from factories import make_risk_decision_reject

        with pytest.raises(ValidationError, match="approved"):
            make_risk_decision_reject(fixed_start, approved_quantity=Decimal("0.1"))
