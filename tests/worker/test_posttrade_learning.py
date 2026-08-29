"""DoD: every closed trade produces a traceable postmortem and memory episode.

End-to-end through the paper stack (entry → stop-out → post-trade analysis):

- the canonical metrics land in the post-trade store (PostgreSQL in prod);
- the audit artifact lands in the artifact store (MinIO in prod);
- a semantic lesson lands in the temporal memory (Graphiti episode);
- a human-readable note lands in the Obsidian vault writer;
- post-trade analysis never touches the risk policy object;
- a redelivery is idempotent; a non-reconciled trade blocks the postmortem.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from adapters.tradingagents.mock import MockTradingAgentsAdapter
from adapters.tradingagents.schemas import MockScenario, TradingAgentsRating
from apps.worker.stages.posttrade import PostTradeReconciliationPendingError
from core.clock.clocks import VirtualClock
from core.config.settings import get_settings
from core.domain.enums import OrderState, TradeLifecycleState
from core.events.envelope import build_domain_event
from core.schemas import PostTradeReview, TradeOutcome

from factories import make_trade_outcome
from worker_helpers import PaperStack, build_paper_stack, scripted_snapshots


def long_adapter(clock: VirtualClock) -> MockTradingAgentsAdapter:
    scenario = MockScenario(
        scenario_id="long-eurusd",
        decision_markdown="**Rating**: Buy",
        rating=TradingAgentsRating.BUY,
    )
    return MockTradingAgentsAdapter(scenarios={"EURUSD": scenario}, clock_now=clock.now)


def build_stack(clock: VirtualClock) -> PaperStack:
    source = scripted_snapshots(
        {
            "EURUSD": [
                Decimal("1.10000"),  # cycle 1: entry
                Decimal("1.09700"),  # cycle 2: crosses the stop
            ]
        }
    )
    return build_paper_stack(
        clock=clock,
        settings=get_settings(),
        tradingagents=long_adapter(clock),
        source=source,
    )


def run_two_cycles(stack: PaperStack) -> list:
    events: list = []
    events.extend(stack.runner.run_once())
    stack.clock.advance(timedelta(minutes=5))
    events.extend(stack.runner.run_once())
    return events


class TestPostTradeLearningDoD:
    def test_closed_trade_produces_traceable_postmortem_and_memory(self) -> None:
        clock = VirtualClock(datetime(2026, 8, 27, tzinfo=UTC))
        stack = build_stack(clock)
        policy_before = stack.rt.policy.model_dump(mode="json")
        events = run_two_cycles(stack)

        closed = next(e for e in events if e.event_name == "trade.closed")
        outcome = TradeOutcome.model_validate(closed.payload)
        record = stack.posttrade_store.get_by_trade(outcome.trade_id)
        assert record is not None, "every closed trade must persist a review"
        assert record.postmortem_completed is True

        # ── canonical metrics ─────────────────────────────────────────────────
        metrics = record.metrics
        assert metrics.pnl_gross == outcome.realized_pnl
        assert metrics.pnl_net == outcome.realized_pnl - outcome.costs
        assert metrics.fees == outcome.costs
        assert metrics.holding_seconds >= 0
        assert metrics.r_multiple is not None  # entry RiskDecision captured
        assert metrics.mae_pct is not None and metrics.mfe_pct is not None  # path recorded
        assert metrics.actual_return_pct == pytest.approx(
            float((outcome.exit_price - outcome.entry_price) / outcome.entry_price * 100)
        )
        assert metrics.actual_return_pct < 0
        assert record.verdict == "CONTRADICTED"

        # ── structured review with independent quality analyses ────────────────
        review = PostTradeReview.model_validate(record.review_payload)
        assert review.metrics == metrics
        producers = {quality.producer for quality in review.signal_quality}
        assert {"quant", "llm", "fused", "memory"} <= producers
        assert review.risk_quality is not None and review.risk_quality.approved
        assert review.risk_quality.limits_respected is True
        assert review.execution_quality is not None
        assert review.expected_vs_actual["direction_hit"] == 0.0
        assert review.lessons
        assert review.artifact_ref is not None
        assert review.vault_path is not None
        assert review.vault_path.startswith("50_Postmortems/2026/")

        # ── MinIO artifact (memory twin) ───────────────────────────────────────
        assert review.artifact_ref is not None
        assert stack.artifact_store.exists(review.artifact_ref)
        artifact = stack.artifact_store.get_json(review.artifact_ref)
        assert artifact["trade_context"]["quant"] is not None
        assert artifact["trade_context"]["proposal"] is not None
        assert artifact["trade_context"]["risk_decision"] is not None
        assert artifact["price_path"], "the observed path is embedded"

        # ── Obsidian note ──────────────────────────────────────────────────────
        assert review.vault_path is not None
        note = stack.vault_writer.note(review.vault_path)
        assert note is not None
        assert "Postmortem" in note
        assert "Autogenerated by the OpenTrading post-trade engine" in note

        # ── Graphiti semantic lesson ───────────────────────────────────────────
        episode_event = next(e for e in events if e.event_name == "memory.episode.created")
        content = episode_event.payload["content"]
        assert content["lesson_type"] == "postmortem"
        assert content["verdict"] == "CONTRADICTED"
        assert content["expected_vs_actual"]["direction_hit"] == 0.0
        assert record.episode_id is not None

        # ── terminal bookkeeping ───────────────────────────────────────────────
        reviewed_ids = {
            str(order.order_intent_id)
            for order in stack.execution_store.list_orders()
            if order.state is OrderState.REVIEWED
        }
        assert set(outcome.order_intent_ids) <= reviewed_ids  # every trade order
        reviewed = [
            lc for lc in stack.store.list_lifecycles() if lc.state is TradeLifecycleState.REVIEWED
        ]
        assert len(reviewed) >= 2  # entry + close lifecycles
        actions = {entry.action for entry in stack.audit_sink.entries}
        assert "postmortem.completed" in actions

        # ── INV-1: post-trade analysis never modified the risk policy ─────────
        assert stack.rt.policy.model_dump(mode="json") == policy_before

    def test_redelivery_is_idempotent(self) -> None:
        clock = VirtualClock(datetime(2026, 8, 27, tzinfo=UTC))
        stack = build_stack(clock)
        events = run_two_cycles(stack)
        closed = next(e for e in events if e.event_name == "trade.closed")

        before = len(stack.posttrade_store.list_reviews())
        replay_outputs = stack.pipeline.dispatch(stack.rt, closed)
        after = len(stack.posttrade_store.list_reviews())

        assert before == after == 1
        assert replay_outputs == []  # stage already succeeded for this trace

    def test_unreconciled_trade_blocks_postmortem(self) -> None:
        clock = VirtualClock(datetime(2026, 8, 27, tzinfo=UTC))
        stack = build_stack(clock)
        stack.runner.seed_account()
        outcome = make_trade_outcome(
            clock.now(),
            position_id="paper:EURUSD:adopted",
            order_intent_ids=[str(uuid4())],  # unknown to the execution store
        )
        event = build_domain_event(
            event_name="trade.closed",
            payload=outcome,
            clock=clock,
            producer="tests.posttrade",
            trace_id=uuid4(),
        )

        with pytest.raises(PostTradeReconciliationPendingError):
            stack.pipeline.dispatch(stack.rt, event)

        assert stack.posttrade_store.list_reviews() == ()
        actions = {entry.action for entry in stack.audit_sink.entries}
        assert "posttrade.reconciliation.pending" in actions
