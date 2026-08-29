"""DoD: the entire research-to-trade lifecycle runs automatically in PAPER
mode and is fully persisted/auditable (Phase 7 Definition of Done).

Scenario (deterministic, virtual clock):

1. cycle 1 — EURUSD snapshot 1.10000; quant momentum + TradingAgents agree
   LONG → fused signal → proposal → risk APPROVE → order intent → Nautilus
   paper fill → POSITION_OPEN, with the canonical stop/take attached;
2. cycle 2 — EURUSD snapshot 1.09700 crosses the stop → the position manager
   emits a close proposal → risk → order → paper fill → TradeOutcome →
   accounting (balance/streak) → postmortem + memory episode.

Assertions cover: the full event chain, trace_id propagation through every
event, persisted runs/lifecycles/orders/positions/account, and the audit trail.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from adapters.tradingagents.mock import MockTradingAgentsAdapter
from adapters.tradingagents.schemas import MockScenario, TradingAgentsRating
from apps.worker.stages.posttrade import PosttradeStage
from core.clock.clocks import VirtualClock
from core.config.settings import get_settings
from core.domain.enums import OrderState, PipelineStageName, TradeLifecycleState
from core.observability.tracing import NullObservation

from factories import make_memory_episode
from worker_helpers import PaperStack, build_paper_stack, scripted_snapshots

ENTRY_EVENTS = (
    "market.snapshot.created",
    "research.requested",
    "quant.signal.created",
    "llm.signal.created",
    "research.completed",
    "research.bundle.created",
    "signal.fused",
    "trade.proposal.created",
    "risk.approved",
    "order.intent.created",
    "order.submitted",
    "order.acknowledged",
    "order.filled",
    "position.updated",
)

CLOSE_EVENTS = (
    "trade.proposal.created",
    "risk.approved",
    "order.intent.created",
    "order.submitted",
    "order.acknowledged",
    "order.filled",
    "trade.closed",
    "postmortem.completed",
    "memory.episode.created",
    "position.updated",
)


def long_adapter(clock: VirtualClock) -> MockTradingAgentsAdapter:
    scenario = MockScenario(
        scenario_id="long-eurusd",
        decision_markdown="**Rating**: Buy",
        rating=TradingAgentsRating.BUY,
    )
    return MockTradingAgentsAdapter(scenarios={"EURUSD": scenario}, clock_now=clock.now)


def build_stack(clock: VirtualClock) -> PaperStack:
    settings = get_settings()
    source = scripted_snapshots(
        {
            "EURUSD": [
                Decimal("1.10000"),  # step 1: entry
                Decimal("1.09700"),  # step 2: crosses the stop
            ]
        }
    )
    stack = build_paper_stack(
        clock=clock,
        settings=settings,
        tradingagents=long_adapter(clock),
        source=source,
    )
    return stack


def run_two_cycles(stack: PaperStack) -> list:
    events: list = []
    events.extend(stack.runner.run_once())
    stack.clock.advance(timedelta(minutes=5))
    events.extend(stack.runner.run_once())
    return events


class RecordingTracer:
    def __init__(self) -> None:
        self.observations: list[tuple[object, str]] = []

    @contextmanager
    def observation(self, **kwargs: Any) -> Iterator[NullObservation]:
        self.observations.append((kwargs["trace_id"], kwargs["name"]))
        yield NullObservation()


class TestEndToEndDoD:
    def test_one_observability_trace_covers_research_both_executions_and_postmortem(self) -> None:
        clock = VirtualClock(datetime(2026, 8, 27, tzinfo=UTC))
        stack = build_stack(clock)
        recording = RecordingTracer()
        stack.rt.telemetry = recording  # type: ignore[assignment]

        events = run_two_cycles(stack)
        trade_trace = next(
            event.trace_id for event in events if event.event_name == "research.requested"
        )
        names = [name for trace_id, name in recording.observations if trace_id == trade_trace]

        assert "pipeline.research" in names
        assert names.count("pipeline.execution") >= 2  # entry and closing fill
        assert "trade.postmortem" in names

    def test_full_lifecycle_persisted_and_auditable(self) -> None:
        clock = VirtualClock(datetime(2026, 8, 27, tzinfo=UTC))
        stack = build_stack(clock)
        memory = stack.rt.extras["memory"]
        memory.ingest(
            make_memory_episode(
                clock.now(),
                content={"stance": "LONG", "instrument_id": "EURUSD"},
            ),
            source="test.seed",
            event_time=clock.now(),
            available_time=clock.now(),
            ingested_at=clock.now(),
        )
        events = run_two_cycles(stack)

        # ── the full canonical chain ran ──────────────────────────────────────
        names = [event.event_name for event in events]
        assert "market.snapshot.created" in names
        assert "research.bundle.created" in names
        assert "signal.fused" in names
        assert "trade.proposal.created" in names
        assert "risk.approved" in names
        assert "order.intent.created" in names
        assert "order.filled" in names
        assert "position.updated" in names
        assert "trade.closed" in names
        assert "postmortem.completed" in names
        assert "memory.episode.created" in names

        # ── trace_id propagation: every event carries a trace, and each
        #    chain's events share the chain's trace ───────────────────────────
        assert all(event.trace_id is not None for event in events)
        first_research = next(e for e in events if e.event_name == "research.requested")
        entry_trace = first_research.trace_id
        entry_chain_names = {e.event_name for e in events if e.trace_id == entry_trace}
        assert set(ENTRY_EVENTS) <= entry_chain_names
        closed_event = next(e for e in events if e.event_name == "trade.closed")
        close_trace = closed_event.trace_id
        close_chain_names = {e.event_name for e in events if e.trace_id == close_trace}
        assert set(CLOSE_EVENTS) <= close_chain_names
        assert entry_trace != close_trace  # the entry and exit are distinct trades

        # ── persisted order lifecycle (INV-6) ─────────────────────────────────
        orders = stack.execution_store.list_orders()
        assert len(orders) >= 2  # entry + close
        assert all(order.venue == "PAPER" for order in orders)
        states = {order.state for order in orders}
        assert OrderState.REVIEWED in states

        # ── position opened then closed (and the platform may re-enter) ──────
        all_positions = stack.execution_store.list_positions(open_only=False)
        assert len(all_positions) >= 1
        assert any(p.closed_at is not None for p in all_positions)
        open_positions = stack.execution_store.list_positions(open_only=True)
        assert len(open_positions) <= 1  # netting: at most one position per venue

        # ── trade outcome persisted and accounted ─────────────────────────────
        outcomes = stack.ledger.outcomes()
        assert len(outcomes) == 1
        outcome = outcomes[0]
        assert outcome.exit_reason == "position_closed"
        assert outcome.realized_pnl != Decimal("0")
        account = stack.store.get_account(stack.config.account_id)
        assert account is not None
        assert account.version > 1
        assert account.realized_pnl != Decimal("0")
        assert account.balance == stack.config.starting_balance + account.realized_pnl

        # The point-in-time memory stance captured at entry must survive into
        # the postmortem instead of being reported as a missing producer.
        entry_context = stack.store.get_context(entry_trace)
        assert entry_context is not None
        assert "memory" in entry_context.fragments
        assert "source_data" in entry_context.fragments
        assert "order_intent" in entry_context.fragments
        review = stack.posttrade_store.get_by_trade(outcome.trade_id)
        assert review is not None
        memory_quality = next(
            quality
            for quality in review.review_payload["signal_quality"]
            if quality["producer"] == "memory"
        )
        assert memory_quality["present"] is True

        # ── lifecycles reached terminal REVIEWED state ────────────────────────
        lifecycles = stack.store.list_lifecycles()
        reviewed = [lc for lc in lifecycles if lc.state is TradeLifecycleState.REVIEWED]
        assert len(reviewed) >= 2  # entry lifecycle + close lifecycle

        # ── every stage left a run record ─────────────────────────────────────
        stages = {run.stage for run in stack.store.list_runs()}
        for stage_name in (
            PipelineStageName.INGEST,
            PipelineStageName.RESEARCH,
            PipelineStageName.FUSION,
            PipelineStageName.PROPOSAL,
            PipelineStageName.RISK,
            PipelineStageName.ORDER_INTENT,
            PipelineStageName.EXECUTION,
            PipelineStageName.POSITIONS,
            PipelineStageName.ACCOUNTING,
            PipelineStageName.POSTTRADE,
        ):
            assert stage_name in stages

        # ── audit trail records the governance-relevant transitions ───────────
        audit_actions = {entry.action for entry in stack.audit_sink.entries}
        assert "trade.proposal.created" in audit_actions
        assert "order.intent.created" in audit_actions
        assert "paper.account.updated" in audit_actions

    def test_no_llm_failure_and_flat_signals_trade_nothing(self) -> None:
        """A FLAT fused signal completes the trace without touching account
        state (INV-1)."""
        clock = VirtualClock(datetime(2026, 8, 27, tzinfo=UTC))
        settings = get_settings()
        flat_adapter = MockTradingAgentsAdapter(
            scenarios={
                "EURUSD": MockScenario(
                    scenario_id="flat",
                    decision_markdown="**Rating**: Hold",
                    rating=TradingAgentsRating.HOLD,
                )
            },
            clock_now=clock.now,
        )
        stack = build_paper_stack(
            clock=clock,
            settings=settings,
            tradingagents=flat_adapter,
            source=scripted_snapshots(
                {"EURUSD": [Decimal("1.10000"), Decimal("1.10000")]}  # quant FLAT too
            ),
        )
        events = run_two_cycles(stack)
        assert all(e.event_name != "trade.proposal.created" for e in events)
        account = stack.store.get_account(stack.config.account_id)
        assert account is not None
        assert account.realized_pnl == Decimal("0")
        assert account.version == 1  # account never updated

    def test_persisted_postmortem_replay_finishes_terminal_bookkeeping(self, monkeypatch) -> None:
        clock = VirtualClock(datetime(2026, 8, 27, tzinfo=UTC))
        stack = build_stack(clock)
        events = run_two_cycles(stack)
        closed_event = next(event for event in events if event.event_name == "trade.closed")
        outcome = stack.ledger.outcomes()[0]

        reviewed: list = []
        cleared: list = []
        monkeypatch.setattr(
            stack.rt.extras["applier"],
            "record_reviewed",
            lambda order_id: reviewed.append(order_id),
        )
        monkeypatch.setattr(
            stack.ledger,
            "clear_price_path",
            lambda position_id: cleared.append(position_id),
        )

        replay_events = PosttradeStage().process(stack.rt, closed_event)

        assert len(reviewed) == len(outcome.order_intent_ids)
        assert cleared == [outcome.position_id]
        assert [event.event_name for event in replay_events] == ["postmortem.completed"]
