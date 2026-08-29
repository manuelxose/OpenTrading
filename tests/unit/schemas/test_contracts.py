"""Schema validation tests: every contract validates, bad input is rejected."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from core.domain.enums import (
    ExperimentStatus,
    OperatingMode,
    OrderType,
    PromotionAction,
    RiskDecisionType,
    RiskReasonCode,
    SignalDirection,
    StrategyState,
)
from core.schemas import CANONICAL_CONTRACTS
from core.schemas.signals import SignalComponent
from pydantic import ValidationError

from factories import (
    FACTORY_BY_NAME,
    make_execution_report,
    make_experiment_run,
    make_fused_signal,
    make_instrument,
    make_market_snapshot,
    make_memory_episode,
    make_order_intent,
    make_promotion_decision,
    make_risk_decision_approve,
    make_risk_decision_reject,
    make_trade_outcome,
)


@pytest.mark.parametrize("name", sorted(CANONICAL_CONTRACTS))
def test_contract_constructs(name: str, fixed_start: datetime) -> None:
    factory = FACTORY_BY_NAME[name]
    obj = factory(fixed_start)
    assert obj.schema_version == "1.0.0"
    if hasattr(obj, "produced_at"):
        assert obj.produced_at == fixed_start


@pytest.mark.parametrize("name", sorted(CANONICAL_CONTRACTS))
def test_contract_rejects_unknown_fields(name: str, fixed_start: datetime) -> None:
    factory = FACTORY_BY_NAME[name]
    with pytest.raises(ValidationError):
        factory(fixed_start, not_a_field=True)


@pytest.mark.parametrize("name", sorted(k for k in CANONICAL_CONTRACTS if k != "DomainEvent"))
def test_schema_version_is_pinned(name: str, fixed_start: datetime) -> None:
    factory = FACTORY_BY_NAME[name]
    with pytest.raises(ValidationError):
        factory(fixed_start, schema_version="2.0.0")


@pytest.mark.parametrize("name", sorted(k for k in CANONICAL_CONTRACTS if k != "DomainEvent"))
def test_naive_timestamp_rejected(name: str, fixed_start: datetime) -> None:
    factory = FACTORY_BY_NAME[name]
    with pytest.raises(ValidationError):
        factory(fixed_start, produced_at=fixed_start.replace(tzinfo=None))


class TestMarketSnapshot:
    def test_source_after_as_of_rejected(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="as_of"):
            make_market_snapshot(
                fixed_start,
                source_timestamp=fixed_start.replace(hour=11),
                as_of=fixed_start,
            )

    def test_inverted_spread_rejected(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="ask"):
            make_market_snapshot(fixed_start, bid=Decimal("1.09"), ask=Decimal("1.08"))

    def test_mid_price(self, fixed_start: datetime) -> None:
        snapshot = make_market_snapshot(fixed_start)
        assert snapshot.mid == (snapshot.bid + snapshot.ask) / 2


class TestInstrument:
    def test_min_lot_above_max_rejected(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="min_lot"):
            make_instrument(fixed_start, min_lot=Decimal("100"), max_lot=Decimal("1"))


class TestRiskDecision:
    def test_approve_requires_approved_values(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="approved_quantity"):
            make_risk_decision_approve(fixed_start, approved_quantity=None)

    def test_approve_rejects_reason_codes(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="reason_codes"):
            make_risk_decision_approve(fixed_start, reason_codes=[RiskReasonCode.STALE_QUOTES])

    def test_reject_requires_reason_codes(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="reason_code"):
            make_risk_decision_reject(fixed_start, reason_codes=[])

    def test_reject_forbids_approved_values(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="approved"):
            make_risk_decision_reject(fixed_start, approved_quantity=Decimal("0.1"))

    def test_decision_field_is_enum(self, fixed_start: datetime) -> None:
        decision = make_risk_decision_approve(fixed_start)
        assert decision.decision is RiskDecisionType.APPROVE


class TestOrderIntent:
    def test_research_mode_cannot_submit(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="does not allow order submission"):
            make_order_intent(fixed_start, operating_mode=OperatingMode.RESEARCH)

    def test_backtest_mode_can_submit_to_simulated_venue(self, fixed_start: datetime) -> None:
        # ADR-0007: OrderIntent is the canonical crossing object for BACKTEST
        # (Nautilus simulated venue, virtual clock), PAPER and LIVE alike.
        intent = make_order_intent(fixed_start, operating_mode=OperatingMode.BACKTEST)
        assert intent.operating_mode is OperatingMode.BACKTEST

    def test_limit_order_requires_price(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="price"):
            make_order_intent(fixed_start, order_type=OrderType.LIMIT, price=None)

    def test_zero_quantity_rejected(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError):
            make_order_intent(fixed_start, quantity=Decimal("0"))


class TestExecutionReport:
    def test_filled_requires_quantity(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="filled_quantity"):
            make_execution_report(fixed_start, filled_quantity=Decimal("0"))


class TestTradeOutcome:
    def test_closed_before_opened_rejected(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="closed_at"):
            make_trade_outcome(
                fixed_start, opened_at=fixed_start, closed_at=fixed_start.replace(hour=6)
            )


class TestFusedSignal:
    def test_weights_must_sum_to_one(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="sum to 1"):
            make_fused_signal(
                fixed_start,
                components=[
                    SignalComponent(
                        name="quant",
                        score=0.8,
                        weight=0.9,
                    )
                ],
            )

    def test_strength_must_match_weighted_scores(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="weighted sum"):
            make_fused_signal(fixed_start, fused_strength=0.1)

    def test_positive_net_requires_long_direction(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="positive net score requires direction LONG"):
            make_fused_signal(
                fixed_start,
                direction=SignalDirection.SHORT,
                components=[SignalComponent(name="quant", score=0.8, weight=1.0)],
                fused_strength=0.8,
            )

    def test_flat_requires_zero_net_and_strength(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="FLAT"):
            make_fused_signal(
                fixed_start,
                direction=SignalDirection.LONG,
                components=[SignalComponent(name="quant", score=0.0, weight=1.0)],
                fused_strength=0.0,
            )

    def test_component_direction_derives_from_score_sign(self, fixed_start: datetime) -> None:
        long_component = SignalComponent(name="quant", score=0.4, weight=1.0)
        short_component = SignalComponent(name="llm", score=-0.4, weight=1.0)
        flat_component = SignalComponent(name="regime", score=0.0, weight=1.0)
        assert long_component.direction is SignalDirection.LONG
        assert short_component.direction is SignalDirection.SHORT
        assert flat_component.direction is SignalDirection.FLAT

    def test_opposing_signed_components_are_valid(self, fixed_start: datetime) -> None:
        fused = make_fused_signal(
            fixed_start,
            components=[
                SignalComponent(name="quant", score=0.8, weight=0.5),
                SignalComponent(name="llm", score=-0.6, weight=0.5),
            ],
            fused_strength=0.1,
        )
        assert fused.direction is SignalDirection.LONG
        assert fused.fused_strength == pytest.approx(0.1)

    def test_nan_component_score_rejected(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError):
            make_fused_signal(
                fixed_start,
                components=[SignalComponent(name="quant", score=float("nan"), weight=1.0)],
            )


class TestMemoryEpisode:
    def test_valid_until_before_valid_from_rejected(self, fixed_start: datetime) -> None:
        from datetime import timedelta

        with pytest.raises(ValidationError, match="valid_until"):
            make_memory_episode(fixed_start, valid_until=fixed_start - timedelta(hours=2))

    def test_point_in_time_validity(self, fixed_start: datetime) -> None:
        from datetime import timedelta

        episode = make_memory_episode(fixed_start)
        assert episode.is_valid_at(fixed_start)
        assert not episode.is_valid_at(fixed_start - timedelta(hours=2))
        assert episode.is_valid_at(fixed_start + timedelta(days=1))


class TestExperimentRun:
    def test_running_with_finished_at_rejected(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="RUNNING"):
            make_experiment_run(fixed_start, finished_at=fixed_start)

    def test_terminal_requires_finished_at(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="finished_at"):
            make_experiment_run(fixed_start, status=ExperimentStatus.COMPLETED, finished_at=None)


class TestPromotionDecision:
    def test_illegal_transition_rejected(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="Invalid state transition"):
            make_promotion_decision(
                fixed_start,
                from_state=StrategyState.IDEA,
                to_state=StrategyState.LIVE_AUTO,
                decision=PromotionAction.APPROVE,
            )

    def test_reject_requires_same_state(self, fixed_start: datetime) -> None:
        with pytest.raises(ValidationError, match="current state"):
            make_promotion_decision(
                fixed_start,
                decision=PromotionAction.REJECT,
                from_state=StrategyState.CANDIDATE,
                to_state=StrategyState.BACKTESTED,
            )
