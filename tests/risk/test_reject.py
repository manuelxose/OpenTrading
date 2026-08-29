"""Hard-check REJECT paths: every hard violation rejects with its reason code."""

from __future__ import annotations

from datetime import time, timedelta
from decimal import Decimal

from core.domain.enums import RiskDecisionType, RiskReasonCode, StrategyState

from risk_helpers import T0, build_portfolio, evaluate, make_position

EXPECTED_CODE = RiskReasonCode
REJECT = RiskDecisionType.REJECT


class TestStrategyState:
    def test_disabled_strategy_rejects(self) -> None:
        decision = evaluate(strategy={"enabled": False})
        self._assert_reject(decision, EXPECTED_CODE.STRATEGY_INACTIVE)

    def test_retired_strategy_rejects(self) -> None:
        decision = evaluate(strategy={"state": StrategyState.RETIRED})
        self._assert_reject(decision, EXPECTED_CODE.STRATEGY_INACTIVE)

    def test_research_state_rejects(self) -> None:
        decision = evaluate(strategy={"state": StrategyState.CANDIDATE})
        self._assert_reject(decision, EXPECTED_CODE.STRATEGY_INACTIVE)

    def test_strategy_id_mismatch_rejects(self) -> None:
        decision = evaluate(proposal={"strategy_id": "strategy-other"})
        self._assert_reject(decision, EXPECTED_CODE.STRATEGY_INACTIVE)

    def test_strategy_version_mismatch_rejects(self) -> None:
        decision = evaluate(proposal={"strategy_version": "0.0.1"})
        self._assert_reject(decision, EXPECTED_CODE.STRATEGY_INACTIVE)

    @staticmethod
    def _assert_reject(decision, code: RiskReasonCode) -> None:
        assert decision.decision is REJECT
        assert code in decision.reason_codes


class TestWhitelist:
    def test_policy_whitelist_excludes_symbol(self) -> None:
        decision = evaluate(policy={"instrument_whitelist": frozenset({"GBPUSD"})})
        assert decision.decision is REJECT
        assert EXPECTED_CODE.SYMBOL_NOT_WHITELISTED in decision.reason_codes

    def test_empty_policy_whitelist_is_fail_closed(self) -> None:
        decision = evaluate(policy={"instrument_whitelist": frozenset()})
        assert decision.decision is REJECT
        assert EXPECTED_CODE.SYMBOL_NOT_WHITELISTED in decision.reason_codes

    def test_strategy_instrument_restriction_rejects(self) -> None:
        decision = evaluate(strategy={"allowed_instruments": frozenset({"GBPUSD"})})
        assert decision.decision is REJECT
        assert EXPECTED_CODE.SYMBOL_NOT_WHITELISTED in decision.reason_codes

    def test_inactive_instrument_rejects(self) -> None:
        decision = evaluate(instrument={"is_active": False})
        assert decision.decision is REJECT
        assert EXPECTED_CODE.SYMBOL_NOT_WHITELISTED in decision.reason_codes


class TestMarketDataFreshness:
    def test_missing_snapshot_rejects(self) -> None:
        decision = evaluate(snapshot={})
        assert decision.decision is REJECT
        assert EXPECTED_CODE.STALE_QUOTES in decision.reason_codes

    def test_stale_snapshot_rejects(self) -> None:
        decision = evaluate(snapshot={"source_timestamp": T0 - timedelta(seconds=61)})
        assert decision.decision is REJECT
        assert EXPECTED_CODE.STALE_QUOTES in decision.reason_codes

    def test_stale_snapshot_rejects_even_if_everything_else_ok(self) -> None:
        decision = evaluate(
            snapshot={"source_timestamp": T0 - timedelta(seconds=600)},
            proposal={"quantity": Decimal("0.01")},
        )
        assert decision.decision is REJECT
        assert EXPECTED_CODE.STALE_QUOTES in decision.reason_codes


class TestBrokerState:
    def test_broker_disconnected_rejects(self) -> None:
        decision = evaluate(account={"broker_connected": False})
        assert decision.decision is REJECT
        assert EXPECTED_CODE.BROKER_DISCONNECTED in decision.reason_codes

    def test_stale_heartbeat_rejects(self) -> None:
        decision = evaluate(account={"last_heartbeat_at": T0 - timedelta(seconds=61)})
        assert decision.decision is REJECT
        assert EXPECTED_CODE.HEARTBEAT_LOST in decision.reason_codes

    def test_missing_heartbeat_rejects(self) -> None:
        decision = evaluate(account={"last_heartbeat_at": None})
        assert decision.decision is REJECT
        assert EXPECTED_CODE.HEARTBEAT_LOST in decision.reason_codes

    def test_safe_mode_rejects(self) -> None:
        decision = evaluate(account={"safe_mode": True})
        assert decision.decision is REJECT
        assert EXPECTED_CODE.SAFE_MODE_ACTIVE in decision.reason_codes


class TestSchedule:
    def test_outside_session_rejects(self) -> None:
        decision = evaluate(
            policy={
                "session_open_utc": time(14, 0),
                "session_close_utc": time(20, 0),
            }
        )
        assert decision.decision is REJECT
        assert EXPECTED_CODE.TRADING_HOURS_RESTRICTED in decision.reason_codes

    def test_inside_session_approves(self) -> None:
        decision = evaluate(
            policy={
                "session_open_utc": time(9, 0),
                "session_close_utc": time(17, 0),
            }
        )
        assert decision.decision is RiskDecisionType.APPROVE

    def test_non_trading_weekday_rejects(self) -> None:
        decision = evaluate(policy={"trading_days": frozenset({1})})  # Tuesday only
        assert decision.decision is REJECT
        assert EXPECTED_CODE.TRADING_HOURS_RESTRICTED in decision.reason_codes

    def test_overnight_session_accepts_early_hours(self) -> None:
        late = T0.replace(hour=23)
        decision = evaluate(
            t=late,
            policy={
                "session_open_utc": time(22, 0),
                "session_close_utc": time(2, 0),
            },
        )
        assert decision.decision is RiskDecisionType.APPROVE

    def test_overnight_session_rejects_mid_afternoon(self) -> None:
        decision = evaluate(
            policy={
                "session_open_utc": time(22, 0),
                "session_close_utc": time(2, 0),
            }
        )
        assert decision.decision is REJECT
        assert EXPECTED_CODE.TRADING_HOURS_RESTRICTED in decision.reason_codes


class TestLossControls:
    def test_daily_loss_breach_rejects(self) -> None:
        decision = evaluate(account={"daily_pnl": Decimal("-1000")})
        assert decision.decision is REJECT
        assert EXPECTED_CODE.MAX_DAILY_LOSS_REACHED in decision.reason_codes

    def test_daily_loss_breach_rejects_any_proposal(self) -> None:
        for quantity in ("0.01", "0.05", "0.10", "1.00"):
            decision = evaluate(
                account={"daily_pnl": Decimal("-5000")},
                proposal={"quantity": Decimal(quantity)},
            )
            assert decision.decision is REJECT
            assert EXPECTED_CODE.MAX_DAILY_LOSS_REACHED in decision.reason_codes

    def test_drawdown_breach_rejects(self) -> None:
        decision = evaluate(account={"equity": Decimal("80000"), "peak_equity": Decimal("100000")})
        assert decision.decision is REJECT
        assert EXPECTED_CODE.MAX_DRAWDOWN_REACHED in decision.reason_codes

    def test_cooldown_active_rejects(self) -> None:
        decision = evaluate(
            account={
                "consecutive_losses": 3,
                "last_loss_at": T0 - timedelta(seconds=10),
            }
        )
        assert decision.decision is REJECT
        assert EXPECTED_CODE.LOSS_SEQUENCE_COOLDOWN in decision.reason_codes

    def test_cooldown_expired_approves(self) -> None:
        decision = evaluate(
            account={
                "consecutive_losses": 3,
                "last_loss_at": T0 - timedelta(seconds=301),
            }
        )
        assert decision.decision is RiskDecisionType.APPROVE

    def test_below_streak_threshold_no_cooldown(self) -> None:
        decision = evaluate(
            account={
                "consecutive_losses": 2,
                "last_loss_at": T0 - timedelta(seconds=10),
            }
        )
        assert decision.decision is RiskDecisionType.APPROVE


class TestSimultaneity:
    def test_too_many_positions_rejects(self) -> None:
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
        assert EXPECTED_CODE.MAX_POSITIONS_REACHED in decision.reason_codes

    def test_at_position_cap_approves(self) -> None:
        from core.schemas.risk import PortfolioExposure

        portfolio = build_portfolio(
            T0,
            positions=[
                make_position(T0, "pos-1", "GBPUSD", "LONG", Decimal("1"), Decimal("1.25")),
                make_position(T0, "pos-2", "USDJPY", "SHORT", Decimal("1"), Decimal("150.0")),
            ],
            exposure=PortfolioExposure(
                total_notional=Decimal("275000"),
                by_instrument={
                    "GBPUSD": Decimal("125000"),
                    "USDJPY": Decimal("150000"),
                },
                by_asset_class={"FX": Decimal("275000")},
            ),
        )
        decision = evaluate(portfolio_obj=portfolio, policy={"max_positions": 3})
        assert decision.decision is RiskDecisionType.APPROVE

    def test_too_many_pending_orders_rejects(self) -> None:
        decision = evaluate(
            portfolio={"pending_order_count": 5},
            policy={"max_pending_orders": 5},
        )
        assert decision.decision is REJECT
        assert EXPECTED_CODE.MAX_ORDERS_REACHED in decision.reason_codes

    def test_at_pending_order_cap_approves(self) -> None:
        decision = evaluate(
            portfolio={"pending_order_count": 4},
            policy={"max_pending_orders": 5},
        )
        assert decision.decision is RiskDecisionType.APPROVE
