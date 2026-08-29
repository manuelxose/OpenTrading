"""Event registry: canonical event names → payload contract classes (architecture §14).

Bus transport lands in a later phase (Redis Streams, INV-15); this module defines the
routing/validation layer every producer and consumer plugs into.
"""

from __future__ import annotations

from core.schemas import (
    ExecutionReport,
    ExperimentRun,
    FusedSignal,
    LLMSignal,
    MarketSnapshot,
    MemoryEpisode,
    OrderIntent,
    PositionSnapshot,
    PostTradeReview,
    PromotionDecision,
    QuantSignal,
    ResearchBundle,
    ResearchPacket,
    ResearchRequest,
    RiskDecision,
    StrategyCandidate,
    TradeOutcome,
    TradeProposal,
)
from core.schemas.base import DomainObject
from core.schemas.execution import EmergencyEvent, ReconciliationEvent, SafeModeEvent

__all__ = [
    "CANONICAL_EVENT_PAYLOAD_SCHEMAS",
    "EventRegistry",
    "UnknownEventError",
]


class UnknownEventError(ValueError):
    """Raised when an event name has no registered payload contract."""

    def __init__(self, event_name: str) -> None:
        super().__init__(f"unknown event name {event_name!r}; register a payload contract first")
        self.event_name = event_name


#: Canonical event names from architecture §14 mapped to their payload contracts.
#: Broker channel events (order.submitted … order.rejected) carry ``ExecutionReport``.
#: Reconciliation (INV-6, §9) and SAFE_MODE events carry dedicated payloads.
CANONICAL_EVENT_PAYLOAD_SCHEMAS: dict[str, type[DomainObject]] = {
    "market.snapshot.created": MarketSnapshot,
    "research.requested": ResearchRequest,
    "research.completed": ResearchPacket,
    "research.bundle.created": ResearchBundle,
    "quant.signal.created": QuantSignal,
    "llm.signal.created": LLMSignal,
    "signal.fused": FusedSignal,
    "trade.proposal.created": TradeProposal,
    "risk.approved": RiskDecision,
    "risk.resized": RiskDecision,
    "risk.rejected": RiskDecision,
    "order.intent.created": OrderIntent,
    "order.submitted": ExecutionReport,
    "order.acknowledged": ExecutionReport,
    "order.partially_filled": ExecutionReport,
    "order.filled": ExecutionReport,
    "order.cancelled": ExecutionReport,
    "order.rejected": ExecutionReport,
    "order.reconciled": ReconciliationEvent,
    "reconciliation.divergence": ReconciliationEvent,
    "system.safe_mode.entered": SafeModeEvent,
    "system.safe_mode.exited": SafeModeEvent,
    "system.emergency.activated": EmergencyEvent,
    "system.emergency.deactivated": EmergencyEvent,
    "system.emergency.heartbeat_lost": EmergencyEvent,
    "system.emergency.heartbeat_restored": EmergencyEvent,
    "position.updated": PositionSnapshot,
    "trade.closed": TradeOutcome,
    "postmortem.completed": PostTradeReview,
    "memory.episode.created": MemoryEpisode,
    "strategy.candidate.created": StrategyCandidate,
    "strategy.promoted": PromotionDecision,
    "strategy.retired": PromotionDecision,
    "experiment.created": ExperimentRun,
    "experiment.completed": ExperimentRun,
}


class EventRegistry:
    """Immutable name → payload contract registry used by producers and consumers."""

    def __init__(self, mapping: dict[str, type[DomainObject]]) -> None:
        self._mapping = dict(mapping)

    def payload_schema(self, event_name: str) -> type[DomainObject]:
        try:
            return self._mapping[event_name]
        except KeyError:
            raise UnknownEventError(event_name) from None

    def is_registered(self, event_name: str) -> bool:
        return event_name in self._mapping

    def event_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._mapping))


#: Process-wide canonical registry.
CANONICAL_EVENT_REGISTRY = EventRegistry(CANONICAL_EVENT_PAYLOAD_SCHEMAS)
