"""Execution-state contracts: persistent order lifecycle, positions, broker
reconciliation and Safe Mode (INV-6, architecture §9).

These contracts are the authoritative record of what the platform *believes* the
broker did. They never assume ``send_order() == executed_trade``: every venue
report is applied through :mod:`engines.execution.applier`, every restart runs
:mod:`engines.execution.reconciler` against live broker state, and a material
unexplained divergence flips :mod:`engines.execution.safe_mode` into SAFE_MODE.

``OrderRecord`` / ``ExecutionPosition`` / ``ReconciliationRun`` /
``SafeModeRecord`` are persisted state records (PostgreSQL via
``engines/execution/persistence``), not cross-component events, so they derive
from ``BaseContractModel`` and stay frozen; they are only ever replaced through
the store's compare-and-set ``update_order``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, ClassVar, Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from core.domain.enums import (
    DeadManSwitchReason,
    DiscrepancyCode,
    EmergencyLevel,
    OrderSide,
    OrderState,
    OrderType,
    PositionSide,
)
from core.schemas.base import BaseContractModel, DomainObject, Provenance, UtcDateTime

__all__ = [
    "EXECUTION_SCHEMA_VERSION",
    "LIVE_ORDER_STATES",
    "DeadManSwitchState",
    "EmergencyControlState",
    "EmergencyEvent",
    "ExecutionPosition",
    "OperationalAlert",
    "OrderRecord",
    "ReconciliationDiscrepancy",
    "ReconciliationEvent",
    "ReconciliationRun",
    "SafeModeAlert",
    "SafeModeEvent",
    "SafeModeRecord",
    "StartupOutcome",
]

EXECUTION_SCHEMA_VERSION = "1.0.0"

#: States that mean an order may still be live (working or in flight) at the
#: venue. These are the orders reconciliation must compare against broker state.
LIVE_ORDER_STATES: frozenset[OrderState] = frozenset(
    {
        OrderState.SUBMITTED,
        OrderState.ACKNOWLEDGED,
        OrderState.PARTIALLY_FILLED,
    }
)

#: States that are terminal at the venue but still await reconciliation.
VENUE_TERMINAL_STATES: frozenset[OrderState] = frozenset(
    {
        OrderState.FILLED,
        OrderState.CANCELLED,
        OrderState.REJECTED,
    }
)

#: Relative tolerance for average-entry-price comparison during reconciliation.
DEFAULT_PRICE_TOLERANCE = Decimal("0.005")


class ExecutionContract(BaseContractModel):
    """Frozen, closed, schema-version-pinned base for persisted execution state."""

    SCHEMA_VERSION: ClassVar[str] = EXECUTION_SCHEMA_VERSION

    schema_version: str = Field(default=EXECUTION_SCHEMA_VERSION)

    @model_validator(mode="after")
    def _pin_schema_version(self) -> Self:
        if self.schema_version != self.SCHEMA_VERSION:
            raise ValueError(
                f"{type(self).__name__} requires schema_version "
                f"{self.SCHEMA_VERSION!r}, got {self.schema_version!r}"
            )
        return self


class OrderRecord(ExecutionContract):
    """The single authoritative persisted record for one ``order_intent_id``.

    Keyed by the canonical idempotency key (INV-2). ``version`` is bumped on
    every transition and guarded by compare-and-set in the store, so a process
    restart can always reconstruct *exactly* where the lifecycle stopped.
    """

    order_intent_id: UUID
    state: OrderState
    strategy_id: str = Field(min_length=1)
    strategy_version: str = Field(min_length=1)
    instrument_id: str = Field(min_length=1)
    venue: str | None = None
    side: OrderSide
    order_type: OrderType
    requested_quantity: Decimal = Field(gt=0)
    filled_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    remaining_quantity: Decimal = Field(default=Decimal("0"), ge=0)
    average_fill_price: Decimal | None = Field(default=None, gt=0)
    venue_order_id: str | None = Field(default=None, min_length=1)
    venue_position_id: str | None = Field(default=None, min_length=1)
    commission: Decimal = Field(default=Decimal("0"), ge=0)
    fees: Decimal = Field(default=Decimal("0"), ge=0)
    slippage: Decimal | None = None
    reject_reason: str | None = None
    #: Highest venue event sequence observed (used for resync bookkeeping).
    last_event_sequence: int = Field(default=0, ge=0)
    #: Fingerprints of already-processed venue events (duplicate protection).
    processed_event_ids: tuple[str, ...] = ()
    version: int = Field(ge=1)
    created_at: UtcDateTime
    updated_at: UtcDateTime
    submitted_at: UtcDateTime | None = None
    acknowledged_at: UtcDateTime | None = None
    filled_at: UtcDateTime | None = None
    cancelled_at: UtcDateTime | None = None
    rejected_at: UtcDateTime | None = None
    reconciled_at: UtcDateTime | None = None
    closed_at: UtcDateTime | None = None
    reviewed_at: UtcDateTime | None = None
    reconciliation_note: str | None = None

    @model_validator(mode="after")
    def _check_shape(self) -> Self:
        if self.filled_quantity + self.remaining_quantity > self.requested_quantity:
            raise ValueError("filled + remaining must not exceed requested quantity")
        if self.state in LIVE_ORDER_STATES | {OrderState.ORDER_INTENT} and self.venue is None:
            raise ValueError(f"state {self.state.value} requires a venue")
        if self.state is OrderState.ORDER_INTENT and self.requested_quantity <= 0:
            raise ValueError("ORDER_INTENT requires a positive requested_quantity")
        if self.remaining_quantity <= 0 and self.state in (
            OrderState.SUBMITTED,
            OrderState.ACKNOWLEDGED,
            OrderState.PARTIALLY_FILLED,
        ):
            raise ValueError(f"state {self.state.value} requires remaining_quantity > 0")
        return self


class ExecutionPosition(ExecutionContract):
    """Persisted point-in-time record of one broker-side position."""

    venue_position_id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    instrument_id: str = Field(min_length=1)
    side: PositionSide
    quantity: Decimal = Field(gt=0)
    average_entry_price: Decimal = Field(gt=0)
    order_intent_id: UUID | None = None
    opened_at: UtcDateTime
    updated_at: UtcDateTime
    closed_at: UtcDateTime | None = None

    @model_validator(mode="after")
    def _check_side(self) -> Self:
        if self.side is PositionSide.FLAT:
            raise ValueError("a FLAT position is not a position")
        return self


class ReconciliationDiscrepancy(ExecutionContract):
    """One difference found between persisted state and live broker state."""

    code: DiscrepancyCode
    severity: Literal["EXPLAINABLE", "WARNING", "MATERIAL"]
    order_intent_id: UUID | None = None
    venue_order_id: str | None = None
    venue_position_id: str | None = None
    expected: str | None = None
    observed: str | None = None
    explanation: str = Field(min_length=1)
    resolution: str | None = None


class ReconciliationRun(ExecutionContract):
    """Result of one mandatory reconciliation pass (INV-6, §9)."""

    run_id: UUID
    started_at: UtcDateTime
    compared_at: UtcDateTime
    broker_reachable: bool
    broker_connected: bool = True
    trading_enabled: bool = True
    account: dict[str, Any] | None = None
    discrepancies: tuple[ReconciliationDiscrepancy, ...] = ()
    material_discrepancies: int = Field(default=0, ge=0)
    orders_reconciled: int = Field(default=0, ge=0)
    orders_resolved: int = Field(default=0, ge=0)
    positions_adopted: int = Field(default=0, ge=0)
    positions_closed: int = Field(default=0, ge=0)
    safe_mode_entered: bool = False
    safe_mode_exited: bool = False
    last_sequences: dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_counts(self) -> Self:
        material = sum(1 for d in self.discrepancies if d.severity == "MATERIAL")
        if material != self.material_discrepancies:
            raise ValueError("material_discrepancies must equal the count of MATERIAL items")
        return self


class SafeModeRecord(ExecutionContract):
    """Persisted SAFE_MODE state (singleton row in PostgreSQL)."""

    active: bool
    since: UtcDateTime | None = None
    reason_codes: tuple[str, ...] = ()
    note: str | None = None
    exited_at: UtcDateTime | None = None
    updated_at: UtcDateTime

    @model_validator(mode="after")
    def _check_shape(self) -> Self:
        if self.active and self.since is None:
            raise ValueError("an active SAFE_MODE requires since")
        if self.active and not self.reason_codes:
            raise ValueError("an active SAFE_MODE requires at least one reason code")
        return self


class OperationalAlert(ExecutionContract):
    """Operational alert raised on SAFE_MODE and emergency-control transitions (§31)."""

    alert_id: UUID
    kind: str = Field(min_length=1)
    severity: Literal["CRITICAL", "WARNING", "INFO"]
    title: str = Field(min_length=1)
    detail: str = Field(min_length=1)
    raised_at: UtcDateTime
    run_id: UUID | None = None


#: Compatibility alias — the SAFE_MODE controller historically named this contract.
SafeModeAlert = OperationalAlert


class StartupOutcome(ExecutionContract):
    """Result of the mandatory startup reconciliation procedure."""

    run_id: UUID
    broker_reachable: bool
    safe_mode_active: bool
    safe_mode_reason_codes: tuple[str, ...] = ()
    material_discrepancies: int = Field(default=0, ge=0)
    orders_reconciled: int = Field(default=0, ge=0)


class ReconciliationEvent(DomainObject):
    """Payload for ``order.reconciled`` / ``reconciliation.divergence``."""

    run_id: UUID
    material_discrepancies: int = Field(default=0, ge=0)
    safe_mode_entered: bool = False
    orders_reconciled: int = Field(default=0, ge=0)
    discrepancy_codes: list[str] = Field(default_factory=list)


class SafeModeEvent(DomainObject):
    """Payload for ``system.safe_mode.entered`` / ``system.safe_mode.exited``."""

    active: bool
    reason_codes: list[str] = Field(default_factory=list)
    note: str | None = None
    since: UtcDateTime | None = None


class EmergencyControlState(ExecutionContract):
    """Persisted state of one emergency control (INV-7, architecture §10).

    Keyed by ``(level, target)`` — ``target`` is the strategy id for
    ``STRATEGY_KILL``, the symbol for ``INSTRUMENT_KILL`` and ``None`` for the
    platform-wide levels. Deactivations keep the row (``active=False``) so the
    full activation history is auditable.
    """

    level: EmergencyLevel
    target: str | None = None
    active: bool
    activated_by: str = Field(min_length=1)
    activated_at: UtcDateTime
    reason: str = Field(min_length=1)
    deactivated_by: str | None = None
    deactivate_reason: str | None = None
    deactivated_at: UtcDateTime | None = None
    updated_at: UtcDateTime

    @model_validator(mode="after")
    def _check_shape(self) -> Self:
        targeted = (EmergencyLevel.STRATEGY_KILL, EmergencyLevel.INSTRUMENT_KILL)
        if self.level in targeted and not self.target:
            raise ValueError(f"{self.level.value} requires a target")
        if self.level not in targeted and self.target:
            raise ValueError(f"{self.level.value} does not accept a target")
        if not self.active and self.deactivated_at is None:
            raise ValueError("an inactive control requires deactivated_at")
        return self


class DeadManSwitchState(ExecutionContract):
    """Persisted dead man switch state (singleton row in PostgreSQL).

    ``safe_execution_state`` is the INV-7 safe state entered when the
    Core ↔ MT4 heartbeat is lost: broker-side SL/TP remain untouched, new
    entries are blocked and a CRITICAL alert is raised. Positions are never
    closed automatically unless the emergency policy explicitly enables it.
    """

    dead_man_switch_enabled: bool = True
    heartbeat_timeout_seconds: float = Field(gt=0)
    armed_at: UtcDateTime
    last_heartbeat_at: UtcDateTime | None = None
    safe_execution_state: bool = False
    heartbeat_lost_at: UtcDateTime | None = None
    reason_codes: tuple[str, ...] = ()
    updated_at: UtcDateTime

    @model_validator(mode="after")
    def _check_shape(self) -> Self:
        if self.safe_execution_state:
            if self.heartbeat_lost_at is None:
                raise ValueError("safe execution state requires heartbeat_lost_at")
            if DeadManSwitchReason.HEARTBEAT_LOST.value not in self.reason_codes:
                raise ValueError("safe execution state requires the HEARTBEAT_LOST reason code")
        return self


class EmergencyEvent(DomainObject):
    """Payload for ``system.emergency.*`` domain events (INV-7)."""

    level: EmergencyLevel | None = None
    target: str | None = None
    active: bool
    actor: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    dead_man_switch: bool = False
    safe_execution_state: bool = False


def build_provenance(producer: str, produced_at: UtcDateTime) -> Provenance:
    """Convenience provenance builder shared by the execution engine."""
    return Provenance(producer=producer, produced_at=produced_at)
