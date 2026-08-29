"""Trading lifecycle contracts: proposal → risk → order → execution → position →
trade → post-trade review (INV-1, INV-2, INV-4, INV-6)."""

from __future__ import annotations

from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from core.domain.enums import (
    ExecutionState,
    OperatingMode,
    OrderSide,
    OrderType,
    PositionSide,
    RiskDecisionType,
    RiskReasonCode,
    SignalDirection,
    TimeInForce,
    allows_order_submission,
)
from core.schemas.base import BaseContractModel, DomainObject, UtcDateTime
from core.schemas.posttrade import (
    ExecutionQualityRecord,
    RiskQualityRecord,
    SignalQualityRecord,
    TradeMetrics,
)

__all__ = [
    "AttributionAnalysis",
    "ExecutionAnalysis",
    "ExecutionReport",
    "OrderIntent",
    "PositionSnapshot",
    "PostTradeReview",
    "QuantEvaluation",
    "RiskDecision",
    "RiskEvaluation",
    "ThesisEvaluation",
    "TradeOutcome",
    "TradeProposal",
]


class TradeProposal(DomainObject):
    """What the intelligence layer proposes. LLM sizing/stop values are advisory only (INV-1)."""

    proposal_id: UUID
    strategy_id: str = Field(min_length=1)
    strategy_version: str = Field(min_length=1)
    instrument_id: str = Field(min_length=1)
    operating_mode: OperatingMode
    direction: SignalDirection
    order_type: OrderType
    time_in_force: TimeInForce = TimeInForce.GTC
    quantity: Decimal = Field(gt=0)
    limit_price: Decimal | None = Field(default=None, gt=0)
    stop_loss: Decimal | None = Field(default=None, gt=0)
    take_profit: Decimal | None = Field(default=None, gt=0)
    source_signal_ids: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1)
    expires_at: UtcDateTime | None = None

    @model_validator(mode="after")
    def _check_direction(self) -> Self:
        if self.direction is SignalDirection.FLAT:
            raise ValueError("a trade proposal must be LONG or SHORT")
        return self


class RiskDecision(DomainObject):
    """Deterministic Risk Engine output (INV-4). Never a bare boolean.

    APPROVE carries ``approved_quantity``, ``approved_stop``, ``risk_amount``
    and no reason codes. REJECT carries ``reason_codes`` and no approved values.
    RESIZE (ADR-0018) carries both: the Risk-Engine-computed approved values and
    the reason codes that bounded the size. ``approved_quantity`` is always
    computed by the Risk Engine — never trusted from the proposal.
    """

    decision_id: UUID
    proposal_id: UUID
    decision: RiskDecisionType
    reason_codes: list[RiskReasonCode] = Field(default_factory=list)
    approved_quantity: Decimal | None = Field(default=None, gt=0)
    approved_stop: Decimal | None = Field(default=None, gt=0)
    risk_amount: Decimal | None = Field(default=None, gt=0)
    policy_version: str = Field(min_length=1)
    risk_engine_version: str = Field(min_length=1)
    inputs_hash: str | None = Field(default=None, description="Hash of risk engine inputs")

    @model_validator(mode="after")
    def _check_shape(self) -> Self:
        if self.decision is RiskDecisionType.APPROVE or self.decision is RiskDecisionType.RESIZE:
            if (
                self.approved_quantity is None
                or self.approved_stop is None
                or self.risk_amount is None
            ):
                raise ValueError(
                    f"{self.decision.value} requires approved_quantity, "
                    "approved_stop and risk_amount (INV-4)"
                )
            if self.decision is RiskDecisionType.APPROVE and self.reason_codes:
                raise ValueError("APPROVE must not carry reason_codes")
            if self.decision is RiskDecisionType.RESIZE and not self.reason_codes:
                raise ValueError("RESIZE must carry at least one reason_code (INV-4)")
        else:
            if not self.reason_codes:
                raise ValueError("REJECT must carry at least one reason_code (INV-4)")
            if (
                self.approved_quantity is not None
                or self.approved_stop is not None
                or self.risk_amount is not None
            ):
                raise ValueError("REJECT must not carry approved values")
        return self


class OrderIntent(DomainObject):
    """The only canonical object that crosses the system (INV-2).

    Never ``MT4Order``. ``order_intent_id`` is the idempotency key for every venue.
    """

    order_intent_id: UUID
    risk_decision_id: UUID
    proposal_id: UUID | None = None
    strategy_id: str = Field(min_length=1)
    strategy_version: str = Field(min_length=1)
    instrument_id: str = Field(min_length=1)
    operating_mode: OperatingMode
    side: OrderSide
    order_type: OrderType
    time_in_force: TimeInForce = TimeInForce.GTC
    quantity: Decimal = Field(
        gt=0,
        description=(
            "Order size in venue-natural units (INV-2): instrument BASE UNITS for "
            "simulated venues (BACKTEST/PAPER via Nautilus — approved lots x "
            "contract_size), and LOTS for live venues (LIVE_GATED/LIVE_AUTO via "
            "MT4), where the live gates require quantity == risk-approved "
            "quantity and the MT4 boundary re-validates lot bounds. Producers "
            "convert units at the boundary; venues never convert."
        ),
    )
    price: Decimal | None = Field(default=None, gt=0)
    stop_loss: Decimal | None = Field(default=None, gt=0)
    take_profit: Decimal | None = Field(default=None, gt=0)
    max_slippage: Decimal = Field(default=Decimal("0"), ge=0)
    sequence: int = Field(default=0, ge=0)
    valid_until: UtcDateTime | None = None
    created_by: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_shape(self) -> Self:
        if not allows_order_submission(self.operating_mode):
            raise ValueError(
                f"operating mode {self.operating_mode.value} does not allow order submission"
            )
        if self.order_type is not OrderType.MARKET and self.price is None:
            raise ValueError("LIMIT/STOP/STOP_LIMIT orders require a price")
        return self


class ExecutionReport(DomainObject):
    """Venue-side confirmation. Never assume ``send_order() == executed_trade`` (INV-6)."""

    execution_report_id: UUID
    order_intent_id: UUID
    venue: str = Field(min_length=1)
    venue_order_id: str | None = None
    status: ExecutionState
    filled_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    average_fill_price: Decimal | None = Field(default=None, gt=0)
    commission: Decimal = Field(default=Decimal("0"), ge=0)
    fees: Decimal = Field(default=Decimal("0"), ge=0)
    slippage: Decimal | None = None
    reject_reason: str | None = None
    report_time: UtcDateTime
    sequence: int = Field(ge=0)
    checksum: str | None = Field(default=None, description="Transport integrity (MT4 protocol)")

    @model_validator(mode="after")
    def _check_fill(self) -> Self:
        if self.status is ExecutionState.FILLED and self.filled_quantity <= 0:
            raise ValueError("a FILLED report must have positive filled_quantity")
        return self


class PositionSnapshot(DomainObject):
    """Point-in-time state of one open position."""

    position_id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    strategy_id: str | None = None
    instrument_id: str = Field(min_length=1)
    side: PositionSide
    quantity: Decimal = Field(gt=0)
    average_entry_price: Decimal = Field(gt=0)
    mark_price: Decimal | None = Field(default=None, gt=0)
    unrealized_pnl: Decimal | None = None
    as_of: UtcDateTime

    @model_validator(mode="after")
    def _check_side(self) -> Self:
        if self.side is PositionSide.FLAT:
            raise ValueError("a FLAT position is not a position snapshot")
        return self


class TradeOutcome(DomainObject):
    """Closed-trade result feeding the post-trade learning loop (architecture §15)."""

    trade_id: UUID
    position_id: str | None = None
    order_intent_ids: list[str] = Field(default_factory=list)
    instrument_id: str = Field(min_length=1)
    direction: SignalDirection
    quantity: Decimal = Field(gt=0)
    entry_price: Decimal = Field(gt=0)
    exit_price: Decimal = Field(gt=0)
    realized_pnl: Decimal
    costs: Decimal = Field(default=Decimal("0"), ge=0)
    slippage_total: Decimal | None = None
    r_multiple: float | None = None
    mae: float | None = None
    mfe: float | None = None
    holding_seconds: int | None = Field(default=None, ge=0)
    opened_at: UtcDateTime
    closed_at: UtcDateTime
    exit_reason: str = Field(min_length=1)
    regime_at_entry: str | None = None
    expected_vs_actual: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_shape(self) -> Self:
        if self.direction is SignalDirection.FLAT:
            raise ValueError("a trade outcome must be LONG or SHORT")
        if self.closed_at < self.opened_at:
            raise ValueError("closed_at must be >= opened_at")
        return self


class ExecutionAnalysis(BaseContractModel):
    slippage: Decimal | None = None
    fees: Decimal | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    fill_quality: str | None = None


class AttributionAnalysis(BaseContractModel):
    alpha_contribution: float | None = None
    sources: dict[str, float] = Field(default_factory=dict)


class ThesisEvaluation(BaseContractModel):
    summary: str = Field(min_length=1)
    verdict: str = Field(min_length=1, description="SUPPORTED | CONTRADICTED | INCONCLUSIVE")
    confidence: float = Field(ge=0, le=1)


class QuantEvaluation(BaseContractModel):
    direction_correct: bool | None = None
    calibration_error: float | None = None
    signal_accuracy: float | None = None


class RiskEvaluation(BaseContractModel):
    limits_respected: bool
    mae_used: float | None = None
    notes: list[str] = Field(default_factory=list)


class PostTradeReview(DomainObject):
    """Postmortem per closed trade: execution, attribution, thesis, quant, risk (INV-16).

    The Phase 7 post-trade learning loop populates the full analysis surface:
    ``metrics`` carries the canonical metric block computed by
    ``engines/posttrade``; ``signal_quality`` / ``risk_quality`` /
    ``execution_quality`` hold the independent evaluations of each chain link;
    ``artifact_ref`` / ``vault_path`` point at the MinIO artifact and the
    Obsidian note produced for this review.
    """

    review_id: UUID
    trade_id: UUID
    execution: ExecutionAnalysis
    attribution: AttributionAnalysis
    thesis: ThesisEvaluation | None = None
    quant: QuantEvaluation | None = None
    risk: RiskEvaluation
    metrics: TradeMetrics | None = None
    signal_quality: list[SignalQualityRecord] = Field(default_factory=list)
    risk_quality: RiskQualityRecord | None = None
    execution_quality: ExecutionQualityRecord | None = None
    expected_vs_actual: dict[str, float] = Field(default_factory=dict)
    lessons: list[str] = Field(default_factory=list)
    artifact_ref: str | None = None
    vault_path: str | None = None
    postmortem_completed: bool = False
