"""Canonical domain enums for OpenTrading.

Values are frozen by ``docs/architecture.md`` (v1.0) and
``.ai/rules/architecture-invariants.md``. Do not rename or remove members without an ADR
(INV-12).
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "AssetClass",
    "CandidateStatus",
    "DeadManSwitchReason",
    "DiscrepancyCode",
    "EmergencyLevel",
    "ExecutionState",
    "ExperimentStatus",
    "MemoryLayer",
    "OperatingMode",
    "OrderSide",
    "OrderState",
    "OrderType",
    "PipelineStageName",
    "PipelineStatus",
    "PositionSide",
    "PromotionAction",
    "ResearchStatus",
    "RiskDecisionType",
    "RiskReasonCode",
    "SafeModeAction",
    "SafeModeReason",
    "SignalDirection",
    "StrategyState",
    "TimeInForce",
    "Timeframe",
    "TradeLifecycleState",
    "allows_order_submission",
    "is_live_mode",
]


class OperatingMode(StrEnum):
    """The only five operating modes (INV-8, architecture §5)."""

    RESEARCH = "RESEARCH"
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    LIVE_GATED = "LIVE_GATED"
    LIVE_AUTO = "LIVE_AUTO"


def is_live_mode(mode: OperatingMode) -> bool:
    """True only for the two modes that send real orders to a broker venue."""
    return mode in (OperatingMode.LIVE_GATED, OperatingMode.LIVE_AUTO)


def allows_order_submission(mode: OperatingMode) -> bool:
    """True when the pipeline may submit ``OrderIntent``s to a venue.

    RESEARCH: no orders possible. BACKTEST: simulated via the virtual clock
    (Nautilus simulated venue, ADR-0007). PAPER: simulated orders on live data.
    """
    return mode in (
        OperatingMode.BACKTEST,
        OperatingMode.PAPER,
        OperatingMode.LIVE_GATED,
        OperatingMode.LIVE_AUTO,
    )


class OrderState(StrEnum):
    """Canonical order lifecycle (INV-6, architecture §8)."""

    CANDIDATE = "CANDIDATE"
    RISK_REJECTED = "RISK_REJECTED"
    APPROVED = "APPROVED"
    ORDER_INTENT = "ORDER_INTENT"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    RECONCILED = "RECONCILED"
    CLOSED = "CLOSED"
    REVIEWED = "REVIEWED"


class DiscrepancyCode(StrEnum):
    """Broker reconciliation discrepancy codes (INV-6, architecture §9).

    Severity is carried by :class:`ReconciliationDiscrepancy`, not the code:
    *EXPLAINABLE* discrepancies are auto-resolved deterministically, *WARNING*
    discrepancies are recorded and adopted (broker is authority for price),
    *MATERIAL* discrepancies cannot be explained away and force SAFE_MODE.
    """

    ORDER_ACK_LOST = "ORDER_ACK_LOST"
    ORDER_NEVER_ACKNOWLEDGED = "ORDER_NEVER_ACKNOWLEDGED"
    FILL_EVENT_LOST = "FILL_EVENT_LOST"
    POSITION_EVENT_LOST = "POSITION_EVENT_LOST"
    POSITION_CLOSED_AT_VENUE = "POSITION_CLOSED_AT_VENUE"
    PRICE_DRIFT = "PRICE_DRIFT"
    BROKER_DEGRADED = "BROKER_DEGRADED"
    UNEXPECTED_BROKER_ORDER = "UNEXPECTED_BROKER_ORDER"
    UNEXPECTED_BROKER_POSITION = "UNEXPECTED_BROKER_POSITION"
    MISSING_BROKER_ORDER = "MISSING_BROKER_ORDER"
    QUANTITY_MISMATCH = "QUANTITY_MISMATCH"
    IDENTIFIER_MISMATCH = "IDENTIFIER_MISMATCH"
    OVERFILL = "OVERFILL"
    BROKER_UNREACHABLE = "BROKER_UNREACHABLE"


class SafeModeReason(StrEnum):
    """Why the platform entered SAFE_MODE (INV-6, INV-7)."""

    RECONCILIATION_DIVERGENCE = "RECONCILIATION_DIVERGENCE"
    BROKER_UNREACHABLE = "BROKER_UNREACHABLE"
    OVERFILL_DETECTED = "OVERFILL_DETECTED"
    MANUAL_INTERVENTION = "MANUAL_INTERVENTION"


class SafeModeAction(StrEnum):
    """Action classes gated by SAFE_MODE. Only NEW_ENTRY is blocked."""

    NEW_ENTRY = "NEW_ENTRY"
    RISK_REDUCING = "RISK_REDUCING"
    RECONCILIATION = "RECONCILIATION"
    MONITORING = "MONITORING"


class EmergencyLevel(StrEnum):
    """The four emergency-control levels (INV-7, architecture §10).

    Semantics frozen by architecture §10:

    - ``STRATEGY_KILL`` — disable one strategy (``target`` = strategy id);
    - ``INSTRUMENT_KILL`` — disable one instrument (``target`` = symbol);
    - ``NO_NEW_POSITIONS`` — portfolio kill: block new entries platform-wide;
    - ``EMERGENCY_KILL`` — cancel pending orders + block new entries +
      flatten positions only when the policy explicitly enables it.
    """

    STRATEGY_KILL = "STRATEGY_KILL"
    INSTRUMENT_KILL = "INSTRUMENT_KILL"
    NO_NEW_POSITIONS = "NO_NEW_POSITIONS"
    EMERGENCY_KILL = "EMERGENCY_KILL"


class DeadManSwitchReason(StrEnum):
    """Why the dead man switch engaged (INV-7, architecture §10)."""

    HEARTBEAT_LOST = "HEARTBEAT_LOST"


class StrategyState(StrEnum):
    """Strategy lifecycle (INV-8, architecture §16).

    There is no ``RD-Agent -> LIVE`` edge; research never auto-promotes to real money.
    """

    IDEA = "IDEA"
    CANDIDATE = "CANDIDATE"
    BACKTESTED = "BACKTESTED"
    WALK_FORWARD_OK = "WALK_FORWARD_OK"
    ROBUSTNESS_OK = "ROBUSTNESS_OK"
    PAPER = "PAPER"
    SHADOW = "SHADOW"
    LIVE_GATED = "LIVE_GATED"
    LIVE_AUTO = "LIVE_AUTO"
    RETIRED = "RETIRED"


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class PositionSide(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class OrderType(StrEnum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"


class TimeInForce(StrEnum):
    GTC = "GTC"
    DAY = "DAY"
    IOC = "IOC"
    FOK = "FOK"


class ExecutionState(StrEnum):
    """Venue-side report status carried by ``ExecutionReport``."""

    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIAL_FILL = "PARTIAL_FILL"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class SignalDirection(StrEnum):
    LONG = "LONG"
    SHORT = "SHORT"
    FLAT = "FLAT"


class RiskDecisionType(StrEnum):
    """A Risk Decision is never a bare boolean (INV-4, architecture §7).

    ``RESIZE`` approves a reduced, Risk-Engine-computed quantity and carries both
    the approved values and the reason codes that bounded the size (ADR-0018).
    """

    APPROVE = "APPROVE"
    RESIZE = "RESIZE"
    REJECT = "REJECT"


class RiskReasonCode(StrEnum):
    """Canonical decision reason codes (architecture §7 controls, ADR-0018).

    Used both for ``REJECT`` and for ``RESIZE`` (the codes that bounded the size).
    """

    INSUFFICIENT_MARGIN = "INSUFFICIENT_MARGIN"
    RISK_LIMIT_EXCEEDED = "RISK_LIMIT_EXCEEDED"
    MAX_DAILY_LOSS_REACHED = "MAX_DAILY_LOSS_REACHED"
    MAX_DRAWDOWN_REACHED = "MAX_DRAWDOWN_REACHED"
    EXPOSURE_LIMIT_EXCEEDED = "EXPOSURE_LIMIT_EXCEEDED"
    CONCENTRATION_LIMIT_EXCEEDED = "CONCENTRATION_LIMIT_EXCEEDED"
    LEVERAGE_LIMIT_EXCEEDED = "LEVERAGE_LIMIT_EXCEEDED"
    TURNOVER_LIMIT_EXCEEDED = "TURNOVER_LIMIT_EXCEEDED"
    MAX_POSITIONS_REACHED = "MAX_POSITIONS_REACHED"
    MAX_ORDERS_REACHED = "MAX_ORDERS_REACHED"
    LOSS_SEQUENCE_COOLDOWN = "LOSS_SEQUENCE_COOLDOWN"
    SYMBOL_NOT_WHITELISTED = "SYMBOL_NOT_WHITELISTED"
    STRATEGY_INACTIVE = "STRATEGY_INACTIVE"
    MARKET_CLOSED = "MARKET_CLOSED"
    TRADING_HOURS_RESTRICTED = "TRADING_HOURS_RESTRICTED"
    EVENT_RESTRICTED = "EVENT_RESTRICTED"
    STALE_QUOTES = "STALE_QUOTES"
    SPREAD_TOO_HIGH = "SPREAD_TOO_HIGH"
    SLIPPAGE_CAP_EXCEEDED = "SLIPPAGE_CAP_EXCEEDED"
    INVALID_STOP_DISTANCE = "INVALID_STOP_DISTANCE"
    SIZE_BELOW_MINIMUM = "SIZE_BELOW_MINIMUM"
    SIZE_ABOVE_MAXIMUM = "SIZE_ABOVE_MAXIMUM"
    LOT_STEP_INVALID = "LOT_STEP_INVALID"
    BROKER_DISCONNECTED = "BROKER_DISCONNECTED"
    HEARTBEAT_LOST = "HEARTBEAT_LOST"
    RECONCILIATION_DIVERGENCE = "RECONCILIATION_DIVERGENCE"
    SAFE_MODE_ACTIVE = "SAFE_MODE_ACTIVE"
    POLICY_NOT_FOUND = "POLICY_NOT_FOUND"
    UNKNOWN = "UNKNOWN"


class ResearchStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ExperimentStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class CandidateStatus(StrEnum):
    PROPOSED = "PROPOSED"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"


class PromotionAction(StrEnum):
    """Outcome of a promotion review (INV-8). Approval is never an LLM action."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"
    HOLD = "HOLD"


class MemoryLayer(StrEnum):
    """FinMem-inspired three-layer memory (architecture §9, concepts only)."""

    SHORT_TERM = "SHORT_TERM"
    MEDIUM_TERM = "MEDIUM_TERM"
    LONG_TERM = "LONG_TERM"


class AssetClass(StrEnum):
    FX = "FX"
    EQUITY = "EQUITY"
    COMMODITY = "COMMODITY"
    CRYPTO = "CRYPTO"
    INDEX = "INDEX"
    BOND = "BOND"


class Timeframe(StrEnum):
    M1 = "M1"
    M5 = "M5"
    M15 = "M15"
    M30 = "M30"
    H1 = "H1"
    H4 = "H4"
    D1 = "D1"
    W1 = "W1"
    MN1 = "MN1"


class MarketDataClass(StrEnum):
    """Data domains of the medallion pipeline (architecture §13).

    OHLCV ships first; fundamentals, macro and news plug into the same
    ``raw → bronze → silver → gold`` flow without a redesign because every
    record carries the same three-point temporal envelope.
    """

    OHLCV = "OHLCV"
    FUNDAMENTALS = "FUNDAMENTALS"
    MACRO = "MACRO"
    NEWS = "NEWS"


class DataQualityFlag(StrEnum):
    """Row-level quality flags attached in the silver layer."""

    OK = "OK"
    DUPLICATE = "DUPLICATE"
    STALE = "STALE"
    FUTURE_DATED = "FUTURE_DATED"
    PRICE_ANOMALY = "PRICE_ANOMALY"
    AVAILABLE_TIME_INFERRED = "AVAILABLE_TIME_INFERRED"


class LayerName(StrEnum):
    """Medallion layers; each maps 1:1 to a MinIO bucket (architecture §13)."""

    RAW = "RAW"
    BRONZE = "BRONZE"
    SILVER = "SILVER"
    GOLD = "GOLD"


class DatasetState(StrEnum):
    """Gold dataset versions start OPEN and become immutable once SEALED."""

    OPEN = "OPEN"
    SEALED = "SEALED"


class IngestionStatus(StrEnum):
    STARTED = "STARTED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class PipelineStageName(StrEnum):
    """The canonical stages of the autonomous trading pipeline (architecture §32 Fase 7).

    One pipeline run record per (trace_id, stage); workers skip a stage whose
    record already exists, which is what makes replays idempotent.
    """

    INGEST = "INGEST"
    RESEARCH = "RESEARCH"
    FUSION = "FUSION"
    PROPOSAL = "PROPOSAL"
    RISK = "RISK"
    ORDER_INTENT = "ORDER_INTENT"
    EXECUTION = "EXECUTION"
    POSITIONS = "POSITIONS"
    ACCOUNTING = "ACCOUNTING"
    POSTTRADE = "POSTTRADE"


class PipelineStatus(StrEnum):
    """Lifecycle of a single stage execution inside a pipeline run."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class TradeLifecycleState(StrEnum):
    """High-level lifecycle of one trade from research to post-trade review.

    Complements :class:`OrderState` (venue-level order lifecycle): the
    ``TradeLifecycle`` record links the proposal → risk decision → order →
    position → outcome chain for one ``trace_id``.
    """

    RESEARCHING = "RESEARCHING"
    SIGNAL_FUSED = "SIGNAL_FUSED"
    PROPOSED = "PROPOSED"
    RISK_REJECTED = "RISK_REJECTED"
    RISK_APPROVED = "RISK_APPROVED"
    ORDER_CREATED = "ORDER_CREATED"
    ORDER_REJECTED = "ORDER_REJECTED"
    POSITION_OPEN = "POSITION_OPEN"
    POSITION_CLOSED = "POSITION_CLOSED"
    REVIEWED = "REVIEWED"
    FAILED = "FAILED"
