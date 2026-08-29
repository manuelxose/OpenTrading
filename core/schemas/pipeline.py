"""Autonomous pipeline contracts (Phase 7, architecture §32 Fase 7).

Three persisted state records back the unattended PAPER pipeline:

- :class:`PipelineRunRecord` — one row per ``(trace_id, stage)`` execution.
  Workers treat a completed record as "already done" (idempotent replays after
  worker restarts) and an errored one as recoverable evidence.
- :class:`TradeLifecycle` — the high-level lifecycle of one trace: research →
  proposal → risk → order → position → outcome → review. Guards transitions
  through :mod:`core.domain.state_machines`.
- :class:`PaperAccountRecord` — the authoritative paper account state. Only
  deterministic execution events (fills, closes) may change it — a failed LLM
  analysis never touches this record (INV-1).

These are persisted state records, not cross-component events, so they derive
from :class:`BaseContractModel` (like the execution-state records) and are only
replaced through compare-and-set store methods.
"""

from __future__ import annotations

from decimal import Decimal
from typing import ClassVar, Self
from uuid import UUID

from pydantic import Field, model_validator

from core.domain.enums import (
    PipelineStageName,
    PipelineStatus,
    SignalDirection,
    TradeLifecycleState,
)
from core.schemas.base import BaseContractModel, UtcDateTime

__all__ = [
    "PIPELINE_SCHEMA_VERSION",
    "PaperAccountRecord",
    "PipelineRunRecord",
    "TradeLifecycle",
]

PIPELINE_SCHEMA_VERSION = "1.0.0"

CURRENCY_PATTERN = r"^[A-Z]{3}$"


class PipelineContract(BaseContractModel):
    """Frozen, closed, schema-version-pinned base for persisted pipeline state."""

    SCHEMA_VERSION: ClassVar[str] = PIPELINE_SCHEMA_VERSION

    schema_version: str = Field(default=PIPELINE_SCHEMA_VERSION)

    @model_validator(mode="after")
    def _pin_schema_version(self) -> Self:
        if self.schema_version != self.SCHEMA_VERSION:
            raise ValueError(
                f"{type(self).__name__} requires schema_version "
                f"{self.SCHEMA_VERSION!r}, got {self.schema_version!r}"
            )
        return self


class PipelineRunRecord(PipelineContract):
    """One (trace_id, stage) execution record: the worker's idempotency ledger.

    ``input_refs`` / ``output_refs`` hold canonical ids of consumed and produced
    objects (snapshot ids, signal ids, proposal ids, …) so every transition can
    be reconstructed from PostgreSQL alone after a total restart.
    """

    run_id: UUID
    trace_id: UUID
    cycle_id: str = Field(min_length=1)
    instrument_id: str = Field(min_length=1)
    stage: PipelineStageName
    status: PipelineStatus
    attempt: int = Field(ge=1)
    started_at: UtcDateTime
    completed_at: UtcDateTime | None = None
    error: str | None = None
    input_refs: dict[str, str] = Field(default_factory=dict)
    output_refs: dict[str, str] = Field(default_factory=dict)


class TradeLifecycle(PipelineContract):
    """Authoritative high-level lifecycle for one trade trace.

    Keyed by ``lifecycle_id`` (deterministic UUIDv5 over the trace id); updated
    only through the store's compare-and-set on ``version``. Terminal states are
    RISK_REJECTED / ORDER_REJECTED / REVIEWED / FAILED (see
    ``TRADE_LIFECYCLE_TRANSITIONS``).
    """

    lifecycle_id: UUID
    trace_id: UUID
    proposal_id: UUID | None = None
    strategy_id: str = Field(min_length=1)
    strategy_version: str = Field(min_length=1)
    instrument_id: str = Field(min_length=1)
    state: TradeLifecycleState
    version: int = Field(ge=1)
    direction: SignalDirection | None = None
    risk_decision_id: UUID | None = None
    order_intent_id: UUID | None = None
    position_id: str | None = None
    trade_id: UUID | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    error: str | None = None
    created_at: UtcDateTime
    updated_at: UtcDateTime


class PaperAccountRecord(PipelineContract):
    """Authoritative paper account state consumed by the Risk Engine.

    ``balance`` is starting balance + realized PnL - costs; ``equity`` adds
    unrealized PnL of open positions; ``daily_pnl`` resets with the trading day.
    Only deterministic execution outcomes update these fields (INV-1, INV-4).
    """

    account_id: str = Field(min_length=1)
    currency: str = Field(pattern=CURRENCY_PATTERN)
    balance: Decimal = Field(ge=0)
    equity: Decimal = Field(gt=0)
    realized_pnl: Decimal
    daily_pnl: Decimal
    peak_equity: Decimal = Field(gt=0)
    consecutive_losses: int = Field(ge=0)
    last_loss_at: UtcDateTime | None = None
    open_positions: int = Field(ge=0)
    version: int = Field(ge=1)
    updated_at: UtcDateTime

    @model_validator(mode="after")
    def _check_loss_streak(self) -> Self:
        if self.consecutive_losses > 0 and self.last_loss_at is None:
            raise ValueError("consecutive_losses > 0 requires last_loss_at")
        return self
