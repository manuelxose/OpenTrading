"""Post-trade analysis contracts (Phase 7, architecture §15 "Post-trade
learning loop").

The post-trade learning loop turns a closed-and-reconciled
:class:`~core.schemas.trading.TradeOutcome` into a structured postmortem:

- :class:`TradeMetrics` — the canonical metric block computed deterministically
  by ``engines/posttrade`` (PnL, fees, slippage, R multiple, alpha, MAE, MFE,
  holding time, entry/exit efficiency, signal calibration, prediction error,
  market regime);
- :class:`SignalQualityRecord` / :class:`RiskQualityRecord` /
  :class:`ExecutionQualityRecord` — independent quality evaluations of each
  link of the chain (QuantSignal, LLMSignal, FusedSignal, RiskDecision,
  execution);
- :class:`PostTradeReviewRecord` — the persisted canonical-metrics row stored
  in PostgreSQL (transactional truth, INV-10);
- :class:`TradeContextRecord` — the per-trace context fragments (signals,
  proposal, risk decision) captured while the trade was live, so a review is
  complete even after a worker restart.

The learning loop is strictly read-only over ``RiskDecision`` / ``RiskPolicy``:
post-trade analysis may never modify live risk limits automatically (INV-1).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, ClassVar, Self
from uuid import UUID

from pydantic import Field, model_validator

from core.domain.enums import RiskDecisionType, SignalDirection
from core.schemas.base import BaseContractModel, UtcDateTime

__all__ = [
    "POSTTRADE_SCHEMA_VERSION",
    "ExecutionQualityRecord",
    "PostTradeReviewRecord",
    "RiskQualityRecord",
    "SignalQualityRecord",
    "TradeContextRecord",
    "TradeMetrics",
]

POSTTRADE_SCHEMA_VERSION = "1.0.0"


class PostTradeContract(BaseContractModel):
    """Frozen, closed, schema-version-pinned base for post-trade records."""

    SCHEMA_VERSION: ClassVar[str] = POSTTRADE_SCHEMA_VERSION

    schema_version: str = Field(default=POSTTRADE_SCHEMA_VERSION)

    @model_validator(mode="after")
    def _pin_schema_version(self) -> Self:
        if self.schema_version != self.SCHEMA_VERSION:
            raise ValueError(
                f"{type(self).__name__} requires schema_version "
                f"{self.SCHEMA_VERSION!r}, got {self.schema_version!r}"
            )
        return self


class TradeMetrics(PostTradeContract):
    """Canonical per-trade metrics (architecture §17).

    Semantics (documented in ``engines/posttrade/metrics.py``):

    - ``pnl_gross`` / ``pnl_net`` — realized PnL before / after fees, account
      currency;
    - ``r_multiple`` — net PnL over the risk amount approved by the Risk
      Engine (``None`` when the decision carried no risk amount);
    - ``alpha_pct`` — actual return in excess of the expected return implied
      by the plan (or over ``benchmark_return_pct`` when one is supplied);
    - ``mae_pct`` / ``mfe_pct`` — maximum adverse / favorable excursion during
      the holding window as a percentage of the entry price, derived from the
      observed price path (``None`` when no path was recorded — the loop never
      fabricates excursion data);
    - ``entry_efficiency`` — how much of the favorable extreme was captured at
      exit; ``exit_efficiency`` — where the exit landed in the adverse→favorable
      range (TradingView-style definitions, see metrics.py);
    - ``signal_calibration_error`` — per-producer Brier error
      ``(confidence - hit)²`` with ``hit ∈ {0, 1}`` against the realized move;
    - ``prediction_error_pct`` — |actual - predicted| return in percent.
    """

    pnl_gross: Decimal
    pnl_net: Decimal
    fees: Decimal = Field(default=Decimal("0"), ge=0)
    slippage: Decimal = Field(default=Decimal("0"), ge=0)
    r_multiple: float | None = None
    alpha_pct: float | None = None
    mae_pct: float | None = Field(default=None, ge=0)
    mfe_pct: float | None = Field(default=None, ge=0)
    holding_seconds: int = Field(ge=0)
    entry_efficiency: float | None = None
    exit_efficiency: float | None = Field(default=None, ge=0, le=1)
    signal_calibration_error: dict[str, float] = Field(default_factory=dict)
    prediction_error_pct: float | None = Field(default=None, ge=0)
    market_regime: str = Field(default="unknown", min_length=1)
    expected_return_pct: float | None = None
    actual_return_pct: float | None = None
    benchmark_return_pct: float | None = None
    expected_r: float | None = Field(default=None, ge=0)


class SignalQualityRecord(PostTradeContract):
    """Independent quality evaluation of one signal producer (INV-16).

    ``producer`` is the canonical fusion input name: ``quant``, ``llm``,
    ``fused`` or ``memory``. ``direction_correct`` compares the producer's
    stance against the realized price move; ``brier_error`` is the
    per-observation calibration error ``(confidence - hit)²``.
    """

    producer: str = Field(min_length=1)
    present: bool = True
    direction: SignalDirection | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    direction_correct: bool | None = None
    brier_error: float | None = Field(default=None, ge=0, le=1)
    notes: list[str] = Field(default_factory=list)


class RiskQualityRecord(PostTradeContract):
    """Independent evaluation of the Risk Decision quality.

    ``limits_respected`` reflects the deterministic Risk Engine verdict
    (APPROVE / RESIZE) — post-trade analysis never re-sizes or re-prices risk;
    it only reports how the decision performed against the realized outcome.
    """

    limits_respected: bool
    decision: RiskDecisionType | None = None
    approved: bool = False
    size_respected: bool | None = None
    planned_stop_respected: bool | None = None
    risk_amount: Decimal | None = Field(default=None, gt=0)
    notes: list[str] = Field(default_factory=list)


class ExecutionQualityRecord(PostTradeContract):
    """Independent evaluation of execution quality (costs, slippage)."""

    slippage_pct: float | None = Field(default=None, ge=0)
    fees_pct: float | None = Field(default=None, ge=0)
    latency_ms: int | None = Field(default=None, ge=0)
    fill_quality: str | None = None
    notes: list[str] = Field(default_factory=list)


class PostTradeReviewRecord(PostTradeContract):
    """Persisted canonical-metrics row (PostgreSQL, INV-10).

    One row per closed-and-reconciled trade; ``review_payload`` embeds the full
    :class:`~core.schemas.trading.PostTradeReview` canonical dict so the audit
    trail is reconstructable from PostgreSQL alone.
    """

    review_id: UUID
    trade_id: UUID
    position_id: str | None = None
    instrument_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    strategy_version: str = Field(min_length=1)
    direction: SignalDirection
    opened_at: UtcDateTime
    closed_at: UtcDateTime
    exit_reason: str = Field(min_length=1)
    metrics: TradeMetrics
    verdict: str = Field(min_length=1)
    postmortem_completed: bool = False
    review_payload: dict[str, Any] = Field(default_factory=dict)
    artifact_key: str | None = None
    vault_path: str | None = None
    episode_id: UUID | None = None
    trace_id: UUID | None = None
    created_at: UtcDateTime

    @model_validator(mode="after")
    def _check_shape(self) -> Self:
        if self.direction is SignalDirection.FLAT:
            raise ValueError("a post-trade review must reference a LONG or SHORT trade")
        if self.closed_at < self.opened_at:
            raise ValueError("closed_at must be >= opened_at")
        return self


class TradeContextRecord(PostTradeContract):
    """Context fragments captured for one trade trace while it was live.

    Keyed by the entry trace id; stages append their canonical outputs
    (``quant``, ``llm``, ``fused``, ``proposal``, ``risk_decision``, ``regime``)
    so the post-trade stage can reconstruct the full decision chain without
    replaying the event stream.
    """

    trace_id: UUID
    instrument_id: str = Field(min_length=1)
    fragments: dict[str, dict[str, Any]] = Field(default_factory=dict)
    updated_at: UtcDateTime
