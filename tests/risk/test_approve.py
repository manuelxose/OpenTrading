"""APPROVE paths: the engine accepts the proposal quantity unchanged."""

from __future__ import annotations

from decimal import Decimal

from core.domain.enums import RiskDecisionType, RiskReasonCode

from risk_helpers import (
    BASELINE_RISK,
    CONTRACT_SIZE,
    MID,
    STOP,
    STOP_DISTANCE,
    evaluate,
)


class TestBaselineApprove:
    def test_baseline_approves_proposed_quantity(self) -> None:
        decision = evaluate()
        assert decision.decision is RiskDecisionType.APPROVE
        assert decision.approved_quantity == Decimal("0.10")
        assert decision.approved_stop == STOP
        assert decision.risk_amount == BASELINE_RISK

    def test_approve_has_no_reason_codes(self) -> None:
        decision = evaluate()
        assert decision.reason_codes == []

    def test_risk_amount_is_engine_computed(self) -> None:
        decision = evaluate()
        expected = decision.approved_quantity * CONTRACT_SIZE * STOP_DISTANCE
        assert decision.risk_amount == expected

    def test_policy_and_engine_versions_recorded(self) -> None:
        decision = evaluate()
        assert decision.policy_version == "17.0.0"
        assert decision.risk_engine_version == "1.0.0"

    def test_inputs_hash_present(self) -> None:
        decision = evaluate()
        assert decision.inputs_hash is not None
        assert len(decision.inputs_hash) == 64

    def test_same_inputs_give_identical_decisions(self) -> None:
        from uuid import uuid4

        pinned_proposal_id = uuid4()
        first = evaluate(proposal={"proposal_id": pinned_proposal_id})
        second = evaluate(proposal={"proposal_id": pinned_proposal_id})
        assert first.model_dump(mode="json") == second.model_dump(mode="json")
        assert first.decision_id == second.decision_id
        assert first.inputs_hash == second.inputs_hash

    def test_inputs_hash_changes_with_quantity(self) -> None:
        first = evaluate()
        second = evaluate(proposal={"quantity": Decimal("0.20")})
        assert first.inputs_hash != second.inputs_hash


class TestApproveVariants:
    def test_limit_order_uses_limit_price_as_entry(self) -> None:
        decision = evaluate(proposal={"order_type": "LIMIT", "limit_price": Decimal("1.07800")})
        assert decision.decision is RiskDecisionType.APPROVE
        distance = Decimal("1.07800") - STOP
        expected_risk = Decimal("0.10") * CONTRACT_SIZE * distance
        assert decision.risk_amount == expected_risk

    def test_short_direction_approved(self) -> None:
        decision = evaluate(
            proposal={
                "direction": "SHORT",
                "stop_loss": MID + STOP_DISTANCE,
            }
        )
        assert decision.decision is RiskDecisionType.APPROVE
        assert decision.risk_amount == BASELINE_RISK

    def test_no_heartbeat_requirement_when_configured_zero(self) -> None:
        decision = evaluate(
            account={"last_heartbeat_at": None},
            policy={"heartbeat_max_age_seconds": 0},
        )
        assert decision.decision is RiskDecisionType.APPROVE
        assert RiskReasonCode.HEARTBEAT_LOST not in decision.reason_codes

    def test_exact_risk_budget_boundary_approves(self) -> None:
        decision = evaluate(policy={"max_risk_per_trade": BASELINE_RISK})
        assert decision.decision is RiskDecisionType.APPROVE

    def test_lot_step_exact_proposal_approves(self) -> None:
        decision = evaluate(proposal={"quantity": Decimal("0.10")})
        assert decision.decision is RiskDecisionType.APPROVE
