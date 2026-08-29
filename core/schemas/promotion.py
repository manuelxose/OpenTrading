"""Strategy promotion contract: ``PromotionDecision`` (INV-8, Phase 10+).

Promotion decisions are recorded with full evidence; approval is a deterministic
system or human administrative action — never an LLM (INV-1).
"""

from __future__ import annotations

from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from core.domain.enums import PromotionAction, StrategyState
from core.domain.state_machines import assert_valid_strategy_transition
from core.schemas.base import DomainObject, UtcDateTime

__all__ = ["PromotionDecision"]


class PromotionDecision(DomainObject):
    decision_id: UUID
    strategy_candidate_id: UUID
    from_state: StrategyState
    to_state: StrategyState
    decision: PromotionAction
    evidence: list[str] = Field(default_factory=list)
    metrics_summary: dict[str, float] = Field(default_factory=dict)
    code_sha: str | None = None
    data_hash: str | None = None
    config_version: str | None = None
    requested_by: str = Field(min_length=1)
    approved_by: str = Field(
        min_length=1, description="Deterministic system or human admin — never an LLM (INV-1)"
    )
    conditions: list[str] = Field(default_factory=list)
    valid_until: UtcDateTime | None = None
    validation_receipt_id: UUID | None = Field(
        default=None,
        description="Required deterministic Validation Factory receipt for PAPER eligibility.",
    )

    @model_validator(mode="after")
    def _check_transition(self) -> Self:
        if self.decision is PromotionAction.APPROVE:
            # Raises ValueError (InvalidStateTransition) on illegal transitions (INV-8).
            assert_valid_strategy_transition(self.from_state, self.to_state)
            if self.to_state is StrategyState.PAPER and self.validation_receipt_id is None:
                raise ValueError("PAPER promotion requires a Validation Factory receipt")
            if self.to_state is StrategyState.PAPER:
                raise ValueError(
                    "PAPER transition must be enacted by the validated promotion service, "
                    "not a raw decision"
                )
            if self.to_state is StrategyState.LIVE_AUTO:
                # INV-8 / Phase 11: strategy code and research pipelines can
                # never self-promote into automated live trading. LIVE_GATED →
                # LIVE_AUTO exists only through the operator-authenticated
                # live-auto registry, which writes an immutable audit event.
                raise ValueError(
                    "LIVE_AUTO promotion requires an explicit administrative action "
                    "through the live-auto registry (never a PromotionDecision)"
                )
        elif self.to_state != self.from_state:
            raise ValueError("REJECT/HOLD decisions must keep the candidate in its current state")
        return self
