"""State machine tests: canonical chains, invalid transitions, terminal states."""

from __future__ import annotations

from itertools import pairwise

import pytest
from core.domain.enums import OrderState, StrategyState
from core.domain.state_machines import (
    ORDER_STATE_TRANSITIONS,
    STRATEGY_STATE_TRANSITIONS,
    InvalidStateTransition,
    assert_valid_order_transition,
    assert_valid_strategy_transition,
    is_valid_order_transition,
    is_valid_strategy_transition,
)


class TestOrderStateMachine:
    def test_canonical_chain_walks_to_reviewed(self) -> None:
        chain = [
            OrderState.CANDIDATE,
            OrderState.APPROVED,
            OrderState.ORDER_INTENT,
            OrderState.SUBMITTED,
            OrderState.ACKNOWLEDGED,
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,
            OrderState.RECONCILED,
            OrderState.CLOSED,
            OrderState.REVIEWED,
        ]
        for current, target in pairwise(chain):
            assert is_valid_order_transition(current, target)
            assert_valid_order_transition(current, target)

    def test_rejected_paths(self) -> None:
        assert is_valid_order_transition(OrderState.CANDIDATE, OrderState.RISK_REJECTED)
        assert is_valid_order_transition(OrderState.SUBMITTED, OrderState.REJECTED)
        assert is_valid_order_transition(OrderState.ORDER_INTENT, OrderState.CANCELLED)

    @pytest.mark.parametrize(
        ("current", "target"),
        [
            (OrderState.CANDIDATE, OrderState.ORDER_INTENT),  # skips risk approval
            (OrderState.ORDER_INTENT, OrderState.FILLED),  # skips submission
            (OrderState.REVIEWED, OrderState.CANDIDATE),  # terminal
            (OrderState.RISK_REJECTED, OrderState.APPROVED),  # terminal
            (OrderState.CANDIDATE, OrderState.REVIEWED),  # arbitrary jump
        ],
    )
    def test_invalid_transitions_raise(self, current: OrderState, target: OrderState) -> None:
        assert not is_valid_order_transition(current, target)
        with pytest.raises(InvalidStateTransition) as excinfo:
            assert_valid_order_transition(current, target)
        assert "->" in str(excinfo.value)

    def test_every_state_has_an_entry(self) -> None:
        assert set(ORDER_STATE_TRANSITIONS) == set(OrderState)

    def test_terminal_states_have_no_edges(self) -> None:
        assert ORDER_STATE_TRANSITIONS[OrderState.REVIEWED] == frozenset()
        assert ORDER_STATE_TRANSITIONS[OrderState.RISK_REJECTED] == frozenset()


class TestStrategyStateMachine:
    def test_canonical_chain_walks_to_retired(self) -> None:
        chain = [
            StrategyState.IDEA,
            StrategyState.CANDIDATE,
            StrategyState.BACKTESTED,
            StrategyState.WALK_FORWARD_OK,
            StrategyState.ROBUSTNESS_OK,
            StrategyState.PAPER,
            StrategyState.SHADOW,
            StrategyState.LIVE_GATED,
            StrategyState.LIVE_AUTO,
            StrategyState.RETIRED,
        ]
        for current, target in pairwise(chain):
            assert is_valid_strategy_transition(current, target)
            assert_valid_strategy_transition(current, target)

    @pytest.mark.parametrize(
        ("current", "target"),
        [
            (StrategyState.IDEA, StrategyState.PAPER),  # skips validation
            (StrategyState.CANDIDATE, StrategyState.LIVE_GATED),  # no RD-Agent -> LIVE edge
            (StrategyState.RETIRED, StrategyState.IDEA),  # terminal
            (StrategyState.LIVE_AUTO, StrategyState.SHADOW),  # backwards
        ],
    )
    def test_invalid_transitions_raise(self, current: StrategyState, target: StrategyState) -> None:
        assert not is_valid_strategy_transition(current, target)
        with pytest.raises(InvalidStateTransition):
            assert_valid_strategy_transition(current, target)

    def test_every_state_has_an_entry(self) -> None:
        assert set(STRATEGY_STATE_TRANSITIONS) == set(StrategyState)

    def test_retired_is_terminal(self) -> None:
        assert STRATEGY_STATE_TRANSITIONS[StrategyState.RETIRED] == frozenset()

    def test_non_live_states_can_retire(self) -> None:
        for state in (
            StrategyState.IDEA,
            StrategyState.CANDIDATE,
            StrategyState.BACKTESTED,
            StrategyState.PAPER,
            StrategyState.LIVE_GATED,
        ):
            assert StrategyState.RETIRED in STRATEGY_STATE_TRANSITIONS[state]
