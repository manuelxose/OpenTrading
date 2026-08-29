"""Explicit state machines for the canonical lifecycles.

The machines here are the single authority for valid transitions; engines and services
must call :func:`assert_valid_transition` (or :func:`is_valid_transition`) instead of
hard-coding adjacency.
"""

from __future__ import annotations

from .enums import OrderState, StrategyState, TradeLifecycleState

__all__ = [
    "ORDER_STATE_TRANSITIONS",
    "STRATEGY_STATE_TRANSITIONS",
    "TRADE_LIFECYCLE_TRANSITIONS",
    "InvalidStateTransition",
    "assert_valid_order_transition",
    "assert_valid_strategy_transition",
    "assert_valid_trade_transition",
    "is_valid_order_transition",
    "is_valid_strategy_transition",
    "is_valid_trade_transition",
]


class InvalidStateTransition(ValueError):
    """Raised when a transition is not allowed by the canonical state machine."""

    def __init__(self, current: str, target: str) -> None:
        super().__init__(f"Invalid state transition: {current} -> {target}")
        self.current = current
        self.target = target


# INV-6 order lifecycle: CANDIDATE -> RISK_REJECTED -> APPROVED -> ORDER_INTENT ->
# SUBMITTED -> ACKNOWLEDGED -> PARTIALLY_FILLED -> FILLED -> CANCELLED -> REJECTED ->
# RECONCILED -> CLOSED -> REVIEWED, with the branching edges that execution reality
# requires (fills can be partial then complete; submitted orders can be cancelled).
ORDER_STATE_TRANSITIONS: dict[OrderState, frozenset[OrderState]] = {
    OrderState.CANDIDATE: frozenset({OrderState.RISK_REJECTED, OrderState.APPROVED}),
    OrderState.RISK_REJECTED: frozenset(),
    OrderState.APPROVED: frozenset({OrderState.ORDER_INTENT}),
    OrderState.ORDER_INTENT: frozenset({OrderState.SUBMITTED, OrderState.CANCELLED}),
    OrderState.SUBMITTED: frozenset(
        {OrderState.ACKNOWLEDGED, OrderState.REJECTED, OrderState.CANCELLED}
    ),
    OrderState.ACKNOWLEDGED: frozenset(
        {OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.REJECTED, OrderState.CANCELLED}
    ),
    OrderState.PARTIALLY_FILLED: frozenset(
        {OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.REJECTED, OrderState.CANCELLED}
    ),
    OrderState.FILLED: frozenset({OrderState.RECONCILED, OrderState.CLOSED}),
    OrderState.CANCELLED: frozenset({OrderState.RECONCILED}),
    OrderState.REJECTED: frozenset({OrderState.RECONCILED}),
    OrderState.RECONCILED: frozenset({OrderState.CLOSED}),
    OrderState.CLOSED: frozenset({OrderState.REVIEWED}),
    OrderState.REVIEWED: frozenset(),
}

# INV-8 strategy lifecycle: IDEA -> CANDIDATE -> BACKTESTED -> WALK_FORWARD_OK ->
# ROBUSTNESS_OK -> PAPER -> SHADOW -> LIVE_GATED -> LIVE_AUTO -> RETIRED.
# Any non-live state may also retire directly. There is no RD-Agent -> LIVE edge.
STRATEGY_STATE_TRANSITIONS: dict[StrategyState, frozenset[StrategyState]] = {
    StrategyState.IDEA: frozenset({StrategyState.CANDIDATE, StrategyState.RETIRED}),
    StrategyState.CANDIDATE: frozenset({StrategyState.BACKTESTED, StrategyState.RETIRED}),
    StrategyState.BACKTESTED: frozenset({StrategyState.WALK_FORWARD_OK, StrategyState.RETIRED}),
    StrategyState.WALK_FORWARD_OK: frozenset({StrategyState.ROBUSTNESS_OK, StrategyState.RETIRED}),
    StrategyState.ROBUSTNESS_OK: frozenset({StrategyState.PAPER, StrategyState.RETIRED}),
    StrategyState.PAPER: frozenset({StrategyState.SHADOW, StrategyState.RETIRED}),
    StrategyState.SHADOW: frozenset({StrategyState.LIVE_GATED, StrategyState.RETIRED}),
    StrategyState.LIVE_GATED: frozenset({StrategyState.LIVE_AUTO, StrategyState.RETIRED}),
    StrategyState.LIVE_AUTO: frozenset({StrategyState.RETIRED}),
    StrategyState.RETIRED: frozenset(),
}

# Trade lifecycle (Phase 7 autonomous pipeline): one trace of research → trade →
# review. FLAT fused signals never produce a proposal, so the lifecycle ends at
# SIGNAL_FUSED without further transitions; RISK_REJECTED / ORDER_REJECTED /
# REVIEWED are terminal. FAILED is a terminal error sink reachable from any
# active state (a failed LLM analysis may never corrupt account state).
TRADE_LIFECYCLE_TRANSITIONS: dict[TradeLifecycleState, frozenset[TradeLifecycleState]] = {
    TradeLifecycleState.RESEARCHING: frozenset(
        {TradeLifecycleState.SIGNAL_FUSED, TradeLifecycleState.FAILED}
    ),
    TradeLifecycleState.SIGNAL_FUSED: frozenset(
        {TradeLifecycleState.PROPOSED, TradeLifecycleState.FAILED}
    ),
    TradeLifecycleState.PROPOSED: frozenset(
        {
            TradeLifecycleState.RISK_REJECTED,
            TradeLifecycleState.RISK_APPROVED,
            TradeLifecycleState.FAILED,
        }
    ),
    TradeLifecycleState.RISK_REJECTED: frozenset(),
    TradeLifecycleState.RISK_APPROVED: frozenset(
        {TradeLifecycleState.ORDER_CREATED, TradeLifecycleState.FAILED}
    ),
    TradeLifecycleState.ORDER_CREATED: frozenset(
        {
            TradeLifecycleState.ORDER_REJECTED,
            TradeLifecycleState.POSITION_OPEN,
            # Exit (close) orders never open a position: a filled close order
            # closes an existing one and goes straight to POSITION_CLOSED.
            TradeLifecycleState.POSITION_CLOSED,
            TradeLifecycleState.FAILED,
        }
    ),
    TradeLifecycleState.ORDER_REJECTED: frozenset(),
    TradeLifecycleState.POSITION_OPEN: frozenset(
        {TradeLifecycleState.POSITION_CLOSED, TradeLifecycleState.FAILED}
    ),
    TradeLifecycleState.POSITION_CLOSED: frozenset({TradeLifecycleState.REVIEWED}),
    TradeLifecycleState.REVIEWED: frozenset(),
    TradeLifecycleState.FAILED: frozenset(),
}


def is_valid_order_transition(current: OrderState, target: OrderState) -> bool:
    return target in ORDER_STATE_TRANSITIONS[current]


def is_valid_strategy_transition(current: StrategyState, target: StrategyState) -> bool:
    return target in STRATEGY_STATE_TRANSITIONS[current]


def assert_valid_order_transition(current: OrderState, target: OrderState) -> None:
    if not is_valid_order_transition(current, target):
        raise InvalidStateTransition(current.value, target.value)


def assert_valid_strategy_transition(current: StrategyState, target: StrategyState) -> None:
    if not is_valid_strategy_transition(current, target):
        raise InvalidStateTransition(current.value, target.value)


def is_valid_trade_transition(current: TradeLifecycleState, target: TradeLifecycleState) -> bool:
    return target in TRADE_LIFECYCLE_TRANSITIONS[current]


def assert_valid_trade_transition(
    current: TradeLifecycleState, target: TradeLifecycleState
) -> None:
    if not is_valid_trade_transition(current, target):
        raise InvalidStateTransition(current.value, target.value)
