"""Pipeline contract, state machine and registry tests (Phase 7)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from core.domain.enums import (
    PipelineStageName,
    PipelineStatus,
    SignalDirection,
    TradeLifecycleState,
)
from core.domain.state_machines import (
    TRADE_LIFECYCLE_TRANSITIONS,
    InvalidStateTransition,
    is_valid_trade_transition,
)
from core.events.registry import CANONICAL_EVENT_PAYLOAD_SCHEMAS
from core.schemas import ResearchBundle, TradeProposal
from core.schemas.pipeline import PaperAccountRecord, PipelineRunRecord, TradeLifecycle
from pydantic import ValidationError

NOW = datetime(2026, 8, 27, tzinfo=UTC)


class TestPipelineRunRecord:
    def test_valid_record(self) -> None:
        record = PipelineRunRecord(
            run_id=uuid4(),
            trace_id=uuid4(),
            cycle_id="cycle-1",
            instrument_id="EURUSD",
            stage=PipelineStageName.RESEARCH,
            status=PipelineStatus.SUCCEEDED,
            attempt=1,
            started_at=NOW,
            completed_at=NOW,
        )
        assert record.stage is PipelineStageName.RESEARCH

    def test_schema_version_pinned(self) -> None:
        with pytest.raises(ValidationError):
            PipelineRunRecord(
                run_id=uuid4(),
                trace_id=uuid4(),
                cycle_id="c",
                instrument_id="EURUSD",
                stage=PipelineStageName.RESEARCH,
                status=PipelineStatus.SUCCEEDED,
                attempt=1,
                started_at=NOW,
                schema_version="9.9.9",
            )


class TestTradeLifecycle:
    def test_direction_and_levels(self) -> None:
        lifecycle = TradeLifecycle(
            lifecycle_id=uuid4(),
            trace_id=uuid4(),
            strategy_id="s",
            strategy_version="1",
            instrument_id="EURUSD",
            state=TradeLifecycleState.PROPOSED,
            direction=SignalDirection.LONG,
            stop_loss=Decimal("1.0900"),
            take_profit=Decimal("1.1100"),
            version=1,
            created_at=NOW,
            updated_at=NOW,
        )
        assert lifecycle.stop_loss == Decimal("1.0900")
        assert lifecycle.direction is SignalDirection.LONG

    def test_version_min_one(self) -> None:
        with pytest.raises(ValidationError):
            TradeLifecycle(
                lifecycle_id=uuid4(),
                trace_id=uuid4(),
                strategy_id="s",
                strategy_version="1",
                instrument_id="EURUSD",
                state=TradeLifecycleState.RESEARCHING,
                version=0,
                created_at=NOW,
                updated_at=NOW,
            )


class TestPaperAccountRecord:
    def test_loss_streak_requires_timestamp(self) -> None:
        with pytest.raises(ValidationError):
            PaperAccountRecord(
                account_id="a",
                currency="USD",
                balance=Decimal("1000"),
                equity=Decimal("1000"),
                realized_pnl=Decimal("0"),
                daily_pnl=Decimal("0"),
                peak_equity=Decimal("1000"),
                consecutive_losses=3,
                last_loss_at=None,
                open_positions=0,
                version=1,
                updated_at=NOW,
            )

    def test_currency_pattern(self) -> None:
        with pytest.raises(ValidationError):
            PaperAccountRecord(
                account_id="a",
                currency="US",
                balance=Decimal("1000"),
                equity=Decimal("1000"),
                realized_pnl=Decimal("0"),
                daily_pnl=Decimal("0"),
                peak_equity=Decimal("1000"),
                consecutive_losses=0,
                open_positions=0,
                version=1,
                updated_at=NOW,
            )


class TestTradeLifecycleMachine:
    def test_canonical_edges(self) -> None:
        assert is_valid_trade_transition(
            TradeLifecycleState.RESEARCHING, TradeLifecycleState.SIGNAL_FUSED
        )
        assert is_valid_trade_transition(
            TradeLifecycleState.SIGNAL_FUSED, TradeLifecycleState.PROPOSED
        )
        assert is_valid_trade_transition(
            TradeLifecycleState.PROPOSED, TradeLifecycleState.RISK_APPROVED
        )
        assert is_valid_trade_transition(
            TradeLifecycleState.RISK_APPROVED, TradeLifecycleState.ORDER_CREATED
        )
        assert is_valid_trade_transition(
            TradeLifecycleState.ORDER_CREATED, TradeLifecycleState.POSITION_OPEN
        )
        # exit orders never open a position
        assert is_valid_trade_transition(
            TradeLifecycleState.ORDER_CREATED, TradeLifecycleState.POSITION_CLOSED
        )
        assert is_valid_trade_transition(
            TradeLifecycleState.POSITION_OPEN, TradeLifecycleState.POSITION_CLOSED
        )
        assert is_valid_trade_transition(
            TradeLifecycleState.POSITION_CLOSED, TradeLifecycleState.REVIEWED
        )

    def test_terminal_states(self) -> None:
        for terminal in (
            TradeLifecycleState.RISK_REJECTED,
            TradeLifecycleState.ORDER_REJECTED,
            TradeLifecycleState.REVIEWED,
            TradeLifecycleState.FAILED,
        ):
            assert TRADE_LIFECYCLE_TRANSITIONS[terminal] == frozenset()

    def test_invalid_transition_refused(self) -> None:
        with pytest.raises(InvalidStateTransition):
            from core.domain.state_machines import assert_valid_trade_transition

            assert_valid_trade_transition(
                TradeLifecycleState.REVIEWED, TradeLifecycleState.PROPOSED
            )


class TestEventRegistry:
    def test_pipeline_events_registered(self) -> None:
        assert CANONICAL_EVENT_PAYLOAD_SCHEMAS["trade.proposal.created"] is TradeProposal
        assert CANONICAL_EVENT_PAYLOAD_SCHEMAS["research.bundle.created"] is ResearchBundle
