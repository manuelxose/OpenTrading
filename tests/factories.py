"""Object factories for tests — one valid instance of every canonical contract.

All timestamps are timezone-aware UTC and come from the caller (usually a
``VirtualClock`` fixture), so tests stay deterministic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from core.domain.enums import (
    AssetClass,
    CandidateStatus,
    EmergencyLevel,
    ExecutionState,
    ExperimentStatus,
    MemoryLayer,
    OperatingMode,
    OrderSide,
    OrderType,
    PositionSide,
    PromotionAction,
    RiskDecisionType,
    RiskReasonCode,
    SignalDirection,
    StrategyState,
    Timeframe,
)
from core.schemas import (
    AccountState,
    DeadManSwitchState,
    EmergencyControlState,
    EmergencyEvent,
    ExecutionReport,
    ExperimentRun,
    FactorCandidate,
    FusedSignal,
    Instrument,
    LLMSignal,
    MarketSnapshot,
    MemoryEpisode,
    ModelCandidate,
    OrderIntent,
    PortfolioExposure,
    PortfolioState,
    PositionSnapshot,
    PostTradeReview,
    PromotionDecision,
    QuantSignal,
    ReconciliationEvent,
    ResearchPacket,
    ResearchRequest,
    RiskDecision,
    RiskPolicy,
    SafeModeEvent,
    StrategyCandidate,
    StrategyConfiguration,
    TradeOutcome,
    TradeProposal,
)
from core.schemas.base import Provenance
from core.schemas.events import DomainEvent
from core.schemas.fusion import FusionInputs, MemoryContext, RegimeContext, ResearchBundle
from core.schemas.market_data import Bar, RawMarketRecord
from core.schemas.memory import EntityRef, RelationRef
from core.schemas.posttrade import (
    ExecutionQualityRecord,
    RiskQualityRecord,
    SignalQualityRecord,
    TradeMetrics,
)
from core.schemas.research import EvidenceRef
from core.schemas.signals import CommitteeMember, SignalComponent
from core.schemas.trading import (
    AttributionAnalysis,
    ExecutionAnalysis,
    QuantEvaluation,
    RiskEvaluation,
    ThesisEvaluation,
)

FIXED_START = datetime(2026, 1, 5, 10, 0, 0, tzinfo=UTC)
PRODUCER = "tests.factories"


def provenance(t: datetime, producer: str = PRODUCER) -> Provenance:
    return Provenance(producer=producer, produced_at=t)


def _merge(base: dict[str, Any], overrides: dict[str, Any] | None) -> dict[str, Any]:
    merged = {**base}
    if overrides:
        merged.update(overrides)
    return merged


def make_instrument(t: datetime, **overrides: Any) -> Instrument:
    base: dict[str, Any] = {
        "instrument_id": "EURUSD",
        "symbol": "EURUSD",
        "exchange": "FX",
        "asset_class": AssetClass.FX,
        "base_currency": "EUR",
        "quote_currency": "USD",
        "price_precision": 5,
        "tick_size": Decimal("0.00001"),
        "lot_size": Decimal("100000"),
        "lot_step": Decimal("0.01"),
        "min_lot": Decimal("0.01"),
        "max_lot": Decimal("100"),
        "produced_at": t,
        "provenance": provenance(t),
    }
    return Instrument(**_merge(base, overrides))


def make_market_snapshot(t: datetime, **overrides: Any) -> MarketSnapshot:
    base: dict[str, Any] = {
        "instrument_id": "EURUSD",
        "as_of": t,
        "source_timestamp": t,
        "bid": Decimal("1.08000"),
        "ask": Decimal("1.08005"),
        "source": "fixture-feed",
        "produced_at": t,
        "provenance": provenance(t),
    }
    return MarketSnapshot(**_merge(base, overrides))


def make_bar(t: datetime, **overrides: Any) -> Bar:
    base: dict[str, Any] = {
        "instrument_id": "EURUSD",
        "timeframe": Timeframe.M1,
        "event_time": t,
        "available_time": t,
        "ingested_at": t,
        "open": Decimal("1.08000"),
        "high": Decimal("1.08010"),
        "low": Decimal("1.07990"),
        "close": Decimal("1.08005"),
        "volume": Decimal("1000"),
        "source": "fixture-feed",
        "source_record_id": f"bar-{t.isoformat()}",
    }
    return Bar(**_merge(base, overrides))


def make_raw_market_record(t: datetime, **overrides: Any) -> RawMarketRecord:
    base: dict[str, Any] = {
        "source": "fixture-feed",
        "source_record_id": f"raw-{t.isoformat()}",
        "event_time": t,
        "available_time": t,
        "ingested_at": t,
        "payload": {
            "symbol": "EUR/USD",
            "timeframe": "1m",
            "open": "1.08000",
            "high": "1.08010",
            "low": "1.07990",
            "close": "1.08005",
            "volume": "1000",
        },
    }
    return RawMarketRecord(**_merge(base, overrides))


def make_research_request(t: datetime, **overrides: Any) -> ResearchRequest:
    base: dict[str, Any] = {
        "request_id": uuid4(),
        "title": "Test research request",
        "question": "What drives EURUSD returns?",
        "requested_by": "research-pipeline",
        "produced_at": t,
        "provenance": provenance(t),
    }
    return ResearchRequest(**_merge(base, overrides))


def make_research_packet(t: datetime, **overrides: Any) -> ResearchPacket:
    base: dict[str, Any] = {
        "packet_id": uuid4(),
        "request_id": uuid4(),
        "summary": "Findings summary",
        "findings": ["finding one"],
        "evidence": [EvidenceRef(ref_id="evt-1", kind="document", source="corpus-a", valid_at=t)],
        "authors": ["quant-researcher"],
        "produced_at": t,
        "provenance": provenance(t),
    }
    return ResearchPacket(**_merge(base, overrides))


def make_research_bundle(t: datetime, **overrides: Any) -> ResearchBundle:
    base: dict[str, Any] = {
        "bundle_id": uuid4(),
        "instrument_id": "EURUSD",
        "snapshot_ref": "fixture-feed",
        "quant": make_quant_signal(t),
        "llm": make_llm_signal(t),
        "memory": None,
        "regime": None,
        "llm_error": None,
        "as_of": t,
        "produced_at": t,
        "provenance": provenance(t),
    }
    return ResearchBundle(**_merge(base, overrides))


def make_quant_signal(t: datetime, **overrides: Any) -> QuantSignal:
    base: dict[str, Any] = {
        "signal_id": uuid4(),
        "instrument_id": "EURUSD",
        "direction": SignalDirection.LONG,
        "strength": 0.78,
        "confidence": 0.8,
        "model_id": "model-01",
        "model_version": "1.2.0",
        "as_of": t,
        "produced_at": t,
        "provenance": provenance(t),
    }
    return QuantSignal(**_merge(base, overrides))


def make_llm_signal(t: datetime, **overrides: Any) -> LLMSignal:
    base: dict[str, Any] = {
        "signal_id": uuid4(),
        "instrument_id": "EURUSD",
        "direction": SignalDirection.LONG,
        "strength": 0.62,
        "confidence": 0.7,
        "reasoning": "Committee leans long on strong macro data.",
        "committee": [
            CommitteeMember(
                name="bull-analyst",
                role="bull",
                stance=SignalDirection.LONG,
                argument="Positive carry and momentum.",
            )
        ],
        "model_name": "gpt-4o",
        "provider": "openai",
        "prompt_version": "p-1.0",
        "as_of": t,
        "produced_at": t,
        "provenance": provenance(t),
    }
    return LLMSignal(**_merge(base, overrides))


def make_fused_signal(t: datetime, **overrides: Any) -> FusedSignal:
    base: dict[str, Any] = {
        "signal_id": uuid4(),
        "instrument_id": "EURUSD",
        "direction": SignalDirection.LONG,
        "fused_strength": 0.72,
        "confidence": 0.75,
        "components": [
            SignalComponent(name="quant", score=0.8, weight=0.5),
            SignalComponent(name="llm", score=0.6, weight=0.3),
            SignalComponent(name="regime", score=0.7, weight=0.2),
        ],
        "calibration_version": "cal-3",
        "compared_against": ["quant_only", "llm_only", "quant_plus_llm", "baseline"],
        "as_of": t,
        "produced_at": t,
        "provenance": provenance(t),
    }
    return FusedSignal(**_merge(base, overrides))


def make_regime_context(t: datetime, **overrides: Any) -> RegimeContext:
    base: dict[str, Any] = {
        "regime": "trend_up",
        "direction": SignalDirection.LONG,
        "score": 0.7,
        "confidence": 0.65,
        "classifier_version": "regime-v1",
        "source": "engines.regime.v1",
        "as_of": t,
    }
    return RegimeContext(**_merge(base, overrides))


def make_memory_context(t: datetime, **overrides: Any) -> MemoryContext:
    base: dict[str, Any] = {
        "direction": SignalDirection.LONG,
        "score": 0.5,
        "confidence": 0.5,
        "evidence_refs": [
            EvidenceRef(ref_id="ep-1", kind="episode", source="graphiti", valid_at=t)
        ],
        "summary": "Memory leans long on recent episodes.",
        "memory_version": "mem-v1",
        "source": "engines.memory.v1",
        "as_of": t,
    }
    return MemoryContext(**_merge(base, overrides))


def make_fusion_inputs(t: datetime, **overrides: Any) -> FusionInputs:
    base: dict[str, Any] = {
        "quant": make_quant_signal(t),
        "llm": make_llm_signal(t),
        "regime": make_regime_context(t),
        "memory": make_memory_context(t),
    }
    return FusionInputs(**_merge(base, overrides))


def make_trade_proposal(t: datetime, **overrides: Any) -> TradeProposal:
    base: dict[str, Any] = {
        "proposal_id": uuid4(),
        "strategy_id": "strategy-01",
        "strategy_version": "3.1.0",
        "instrument_id": "EURUSD",
        "operating_mode": OperatingMode.PAPER,
        "direction": SignalDirection.LONG,
        "order_type": OrderType.MARKET,
        "quantity": Decimal("0.10"),
        "stop_loss": Decimal("1.07000"),
        "take_profit": Decimal("1.10000"),
        "rationale": "Momentum continuation with tight stop.",
        "produced_at": t,
        "provenance": provenance(t),
    }
    return TradeProposal(**_merge(base, overrides))


def make_risk_decision_approve(t: datetime, **overrides: Any) -> RiskDecision:
    base: dict[str, Any] = {
        "decision_id": uuid4(),
        "proposal_id": uuid4(),
        "decision": RiskDecisionType.APPROVE,
        "approved_quantity": Decimal("0.10"),
        "approved_stop": Decimal("1.07500"),
        "risk_amount": Decimal("94.20"),
        "policy_version": "risk-17",
        "risk_engine_version": "0.1.0",
        "produced_at": t,
        "provenance": provenance(t),
    }
    return RiskDecision(**_merge(base, overrides))


def make_risk_decision_reject(t: datetime, **overrides: Any) -> RiskDecision:
    base: dict[str, Any] = {
        "decision_id": uuid4(),
        "proposal_id": uuid4(),
        "decision": RiskDecisionType.REJECT,
        "reason_codes": [RiskReasonCode.MAX_DAILY_LOSS_REACHED],
        "policy_version": "risk-17",
        "risk_engine_version": "0.1.0",
        "produced_at": t,
        "provenance": provenance(t),
    }
    return RiskDecision(**_merge(base, overrides))


def make_risk_decision_resize(t: datetime, **overrides: Any) -> RiskDecision:
    base: dict[str, Any] = {
        "decision_id": uuid4(),
        "proposal_id": uuid4(),
        "decision": RiskDecisionType.RESIZE,
        "reason_codes": [RiskReasonCode.RISK_LIMIT_EXCEEDED],
        "approved_quantity": Decimal("0.05"),
        "approved_stop": Decimal("1.07500"),
        "risk_amount": Decimal("47.10"),
        "policy_version": "risk-17",
        "risk_engine_version": "0.1.0",
        "produced_at": t,
        "provenance": provenance(t),
    }
    return RiskDecision(**_merge(base, overrides))


def make_risk_policy(t: datetime, **overrides: Any) -> RiskPolicy:
    base: dict[str, Any] = {
        "policy_id": "risk-17",
        "policy_version": "17.0.0",
        "max_risk_per_trade": Decimal("500"),
        "max_total_exposure": Decimal("5000000"),
        "max_instrument_exposure": Decimal("1000000"),
        "max_asset_class_exposure": {AssetClass.FX: Decimal("5000000")},
        "max_currency_exposure": {
            "EUR": Decimal("5000000"),
            "USD": Decimal("5000000"),
        },
        "max_leverage": Decimal("10"),
        "margin_rates": {AssetClass.FX: Decimal("0.05")},
        "max_positions": 5,
        "max_pending_orders": 5,
        "max_daily_loss": Decimal("1000"),
        "max_drawdown_pct": Decimal("0.2"),
        "max_consecutive_losses": 3,
        "cooldown_seconds": 300,
        "max_spread_relative": Decimal("0.001"),
        "max_slippage_relative": Decimal("0.001"),
        "min_stop_distance": Decimal("0.0010"),
        "market_data_max_age_seconds": 60,
        "heartbeat_max_age_seconds": 60,
        "produced_at": t,
        "provenance": provenance(t),
    }
    return RiskPolicy(**_merge(base, overrides))


def make_account_state(t: datetime, **overrides: Any) -> AccountState:
    base: dict[str, Any] = {
        "account_id": "acc-1",
        "currency": "USD",
        "balance": Decimal("100000"),
        "equity": Decimal("100000"),
        "free_margin": Decimal("90000"),
        "leverage": Decimal("30"),
        "peak_equity": Decimal("110000"),
        "daily_pnl": Decimal("50"),
        "consecutive_losses": 0,
        "broker_connected": True,
        "last_heartbeat_at": t,
        "as_of": t,
        "produced_at": t,
        "provenance": provenance(t),
    }
    return AccountState(**_merge(base, overrides))


def make_portfolio_state(t: datetime, **overrides: Any) -> PortfolioState:
    base: dict[str, Any] = {
        "account_id": "acc-1",
        "positions": [],
        "pending_order_count": 0,
        "exposure": PortfolioExposure(),
        "as_of": t,
        "produced_at": t,
        "provenance": provenance(t),
    }
    return PortfolioState(**_merge(base, overrides))


def make_strategy_configuration(t: datetime, **overrides: Any) -> StrategyConfiguration:
    base: dict[str, Any] = {
        "strategy_id": "strategy-01",
        "strategy_version": "3.1.0",
        "enabled": True,
        "state": StrategyState.PAPER,
        "as_of": t,
        "produced_at": t,
        "provenance": provenance(t),
    }
    return StrategyConfiguration(**_merge(base, overrides))


def make_order_intent(t: datetime, **overrides: Any) -> OrderIntent:
    base: dict[str, Any] = {
        "order_intent_id": uuid4(),
        "risk_decision_id": uuid4(),
        "strategy_id": "strategy-01",
        "strategy_version": "3.1.0",
        "instrument_id": "EURUSD",
        "operating_mode": OperatingMode.PAPER,
        "side": OrderSide.BUY,
        "order_type": OrderType.MARKET,
        "quantity": Decimal("0.10"),
        "max_slippage": Decimal("0.00020"),
        "created_by": "risk-engine",
        "produced_at": t,
        "provenance": provenance(t),
    }
    return OrderIntent(**_merge(base, overrides))


def make_execution_report(t: datetime, **overrides: Any) -> ExecutionReport:
    base: dict[str, Any] = {
        "execution_report_id": uuid4(),
        "order_intent_id": uuid4(),
        "venue": "nautilus-paper",
        "status": ExecutionState.FILLED,
        "filled_quantity": Decimal("0.10"),
        "average_fill_price": Decimal("1.08000"),
        "report_time": t,
        "sequence": 1,
        "produced_at": t,
        "provenance": provenance(t),
    }
    return ExecutionReport(**_merge(base, overrides))


def make_position_snapshot(t: datetime, **overrides: Any) -> PositionSnapshot:
    base: dict[str, Any] = {
        "position_id": "pos-1",
        "account_id": "acc-1",
        "strategy_id": "strategy-01",
        "instrument_id": "EURUSD",
        "side": PositionSide.LONG,
        "quantity": Decimal("0.10"),
        "average_entry_price": Decimal("1.08000"),
        "as_of": t,
        "produced_at": t,
        "provenance": provenance(t),
    }
    return PositionSnapshot(**_merge(base, overrides))


def make_trade_outcome(t: datetime, **overrides: Any) -> TradeOutcome:
    base: dict[str, Any] = {
        "trade_id": uuid4(),
        "instrument_id": "EURUSD",
        "direction": SignalDirection.LONG,
        "quantity": Decimal("0.10"),
        "entry_price": Decimal("1.08000"),
        "exit_price": Decimal("1.08500"),
        "realized_pnl": Decimal("50.00"),
        "opened_at": t - timedelta(hours=4),
        "closed_at": t,
        "exit_reason": "take_profit",
        "produced_at": t,
        "provenance": provenance(t),
    }
    return TradeOutcome(**_merge(base, overrides))


def make_posttrade_review(t: datetime, **overrides: Any) -> PostTradeReview:
    base: dict[str, Any] = {
        "review_id": uuid4(),
        "trade_id": uuid4(),
        "execution": ExecutionAnalysis(fill_quality="good"),
        "attribution": AttributionAnalysis(alpha_contribution=0.12),
        "thesis": ThesisEvaluation(summary="Thesis held.", verdict="SUPPORTED", confidence=0.8),
        "quant": QuantEvaluation(direction_correct=True),
        "risk": RiskEvaluation(limits_respected=True),
        "produced_at": t,
        "provenance": provenance(t),
    }
    return PostTradeReview(**_merge(base, overrides))


def make_trade_metrics(t: datetime, **overrides: Any) -> TradeMetrics:
    base: dict[str, Any] = {
        "pnl_gross": Decimal("50.00"),
        "pnl_net": Decimal("48.00"),
        "fees": Decimal("2.00"),
        "slippage": Decimal("1.00"),
        "r_multiple": 1.2,
        "alpha_pct": 0.35,
        "mae_pct": 0.2,
        "mfe_pct": 0.8,
        "holding_seconds": 3600,
        "entry_efficiency": 0.7,
        "exit_efficiency": 0.8,
        "signal_calibration_error": {"quant": 0.16},
        "prediction_error_pct": 0.1,
        "market_regime": "trend_up",
        "expected_return_pct": 0.45,
        "actual_return_pct": 0.80,
        "expected_r": 2.0,
    }
    return TradeMetrics(**_merge(base, overrides))


def make_signal_quality(t: datetime, **overrides: Any) -> SignalQualityRecord:
    base: dict[str, Any] = {
        "producer": "quant",
        "present": True,
        "direction": SignalDirection.LONG,
        "confidence": 0.8,
        "direction_correct": True,
        "brier_error": 0.04,
        "notes": ["direction matched the realized move"],
    }
    return SignalQualityRecord(**_merge(base, overrides))


def make_risk_quality(t: datetime, **overrides: Any) -> RiskQualityRecord:
    base: dict[str, Any] = {
        "limits_respected": True,
        "decision": RiskDecisionType.APPROVE,
        "approved": True,
        "size_respected": True,
        "planned_stop_respected": True,
        "risk_amount": Decimal("100.00"),
        "notes": ["risk-approved at entry"],
    }
    return RiskQualityRecord(**_merge(base, overrides))


def make_execution_quality(t: datetime, **overrides: Any) -> ExecutionQualityRecord:
    base: dict[str, Any] = {
        "slippage_pct": 0.01,
        "fees_pct": 0.02,
        "latency_ms": 5,
        "fill_quality": "paper",
        "notes": ["paper venue fill"],
    }
    return ExecutionQualityRecord(**_merge(base, overrides))


def make_memory_episode(t: datetime, **overrides: Any) -> MemoryEpisode:
    base: dict[str, Any] = {
        "episode_id": uuid4(),
        "layer": MemoryLayer.SHORT_TERM,
        "valid_from": t - timedelta(hours=1),
        "summary": "EURUSD breakout after NFP.",
        "entities": [EntityRef(entity_id="EURUSD", entity_type="Instrument", name="EURUSD")],
        "relations": [RelationRef(source="EURUSD", relation="SUPPORTS", target="thesis-1")],
        "produced_at": t,
        "provenance": provenance(t),
    }
    return MemoryEpisode(**_merge(base, overrides))


def make_factor_candidate(t: datetime, **overrides: Any) -> FactorCandidate:
    base: dict[str, Any] = {
        "candidate_id": uuid4(),
        "name": "momentum_10d",
        "description": "10-day momentum factor",
        "expression": "close / close.shift(10) - 1",
        "status": CandidateStatus.PROPOSED,
        "produced_at": t,
        "provenance": provenance(t),
    }
    return FactorCandidate(**_merge(base, overrides))


def make_model_candidate(t: datetime, **overrides: Any) -> ModelCandidate:
    base: dict[str, Any] = {
        "candidate_id": uuid4(),
        "name": "lightgbm-01",
        "model_type": "LGBMRegressor",
        "framework": "qlib",
        "training_dataset_ref": "ds://eurusd-h1/v3",
        "produced_at": t,
        "provenance": provenance(t),
    }
    return ModelCandidate(**_merge(base, overrides))


def make_strategy_candidate(t: datetime, **overrides: Any) -> StrategyCandidate:
    base: dict[str, Any] = {
        "candidate_id": uuid4(),
        "name": "trend-01",
        "state": StrategyState.CANDIDATE,
        "produced_at": t,
        "provenance": provenance(t),
    }
    return StrategyCandidate(**_merge(base, overrides))


def make_experiment_run(t: datetime, **overrides: Any) -> ExperimentRun:
    base: dict[str, Any] = {
        "experiment_id": uuid4(),
        "name": "exp-01",
        "experiment_type": "FACTOR",
        "dataset_ref": "ds://eurusd-h1/v3",
        "status": ExperimentStatus.RUNNING,
        "started_at": t,
        "produced_at": t,
        "provenance": provenance(t),
    }
    return ExperimentRun(**_merge(base, overrides))


def make_promotion_decision(t: datetime, **overrides: Any) -> PromotionDecision:
    base: dict[str, Any] = {
        "decision_id": uuid4(),
        "strategy_candidate_id": uuid4(),
        "from_state": StrategyState.CANDIDATE,
        "to_state": StrategyState.BACKTESTED,
        "decision": PromotionAction.APPROVE,
        "requested_by": "validation-factory",
        "approved_by": "admin",
        "produced_at": t,
        "provenance": provenance(t),
    }
    return PromotionDecision(**_merge(base, overrides))


def make_reconciliation_event(t: datetime, **overrides: Any) -> ReconciliationEvent:
    base: dict[str, Any] = {
        "run_id": uuid4(),
        "material_discrepancies": 0,
        "safe_mode_entered": False,
        "orders_reconciled": 0,
        "discrepancy_codes": [],
        "produced_at": t,
        "provenance": provenance(t),
    }
    return ReconciliationEvent(**_merge(base, overrides))


def make_safe_mode_event(t: datetime, **overrides: Any) -> SafeModeEvent:
    base: dict[str, Any] = {
        "active": True,
        "reason_codes": ["RECONCILIATION_DIVERGENCE"],
        "note": None,
        "since": t,
        "produced_at": t,
        "provenance": provenance(t),
    }
    return SafeModeEvent(**_merge(base, overrides))


def make_emergency_event(t: datetime, **overrides: Any) -> EmergencyEvent:
    base: dict[str, Any] = {
        "level": EmergencyLevel.NO_NEW_POSITIONS,
        "target": None,
        "active": True,
        "actor": "operator",
        "reason": "test emergency",
        "dead_man_switch": False,
        "safe_execution_state": False,
        "produced_at": t,
        "provenance": provenance(t),
    }
    return EmergencyEvent(**_merge(base, overrides))


def make_emergency_control_state(t: datetime, **overrides: Any) -> EmergencyControlState:
    base: dict[str, Any] = {
        "level": EmergencyLevel.NO_NEW_POSITIONS,
        "target": None,
        "active": True,
        "activated_by": "operator",
        "activated_at": t,
        "reason": "test emergency",
        "deactivated_by": None,
        "deactivate_reason": None,
        "deactivated_at": None,
        "updated_at": t,
    }
    return EmergencyControlState(**_merge(base, overrides))


def make_dead_man_switch_state(t: datetime, **overrides: Any) -> DeadManSwitchState:
    base: dict[str, Any] = {
        "dead_man_switch_enabled": True,
        "heartbeat_timeout_seconds": 6.0,
        "armed_at": t,
        "last_heartbeat_at": t,
        "safe_execution_state": False,
        "heartbeat_lost_at": None,
        "reason_codes": [],
        "updated_at": t,
    }
    return DeadManSwitchState(**_merge(base, overrides))


def make_domain_event(t: datetime, **overrides: Any) -> DomainEvent:
    base: dict[str, Any] = {
        "event_id": uuid4(),
        "event_time": t,
        "ingested_at": t + timedelta(milliseconds=1),
        "producer": PRODUCER,
        "event_name": "market.snapshot.created",
        "payload": make_market_snapshot(t).canonical_dict(),
        "provenance": {"payload_schema": "MarketSnapshot", "payload_schema_version": "1.0.0"},
    }
    return DomainEvent(**_merge(base, overrides))


#: Name → factory for every contract in CANONICAL_CONTRACTS.
FACTORY_BY_NAME: dict[str, Any] = {
    "Instrument": make_instrument,
    "MarketSnapshot": make_market_snapshot,
    "ResearchRequest": make_research_request,
    "ResearchPacket": make_research_packet,
    "ResearchBundle": make_research_bundle,
    "QuantSignal": make_quant_signal,
    "LLMSignal": make_llm_signal,
    "FusedSignal": make_fused_signal,
    "TradeProposal": make_trade_proposal,
    "RiskDecision": make_risk_decision_approve,
    "RiskPolicy": make_risk_policy,
    "AccountState": make_account_state,
    "PortfolioState": make_portfolio_state,
    "StrategyConfiguration": make_strategy_configuration,
    "ReconciliationEvent": make_reconciliation_event,
    "SafeModeEvent": make_safe_mode_event,
    "EmergencyEvent": make_emergency_event,
    "EmergencyControlState": make_emergency_control_state,
    "DeadManSwitchState": make_dead_man_switch_state,
    "OrderIntent": make_order_intent,
    "ExecutionReport": make_execution_report,
    "PositionSnapshot": make_position_snapshot,
    "TradeOutcome": make_trade_outcome,
    "PostTradeReview": make_posttrade_review,
    "MemoryEpisode": make_memory_episode,
    "FactorCandidate": make_factor_candidate,
    "ModelCandidate": make_model_candidate,
    "StrategyCandidate": make_strategy_candidate,
    "ExperimentRun": make_experiment_run,
    "PromotionDecision": make_promotion_decision,
    "TradeMetrics": make_trade_metrics,
    "SignalQualityRecord": make_signal_quality,
    "RiskQualityRecord": make_risk_quality,
    "ExecutionQualityRecord": make_execution_quality,
    "DomainEvent": make_domain_event,
}
