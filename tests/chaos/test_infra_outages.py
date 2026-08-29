"""Infrastructure outage scenarios (deterministic fault injection).

Each scenario injects the failure at the same seam the production system uses,
then proves the recovery contract:

- **Redis termination** — the real ``RedisStreamBus`` keeps retrying (unattended
  mode), loses nothing while Redis is down, and delivers every queued message
  exactly once after Redis returns; bounded mode surfaces a clean error.
- **PostgreSQL restart** — a store write failing mid-stage leaves the message
  unacked; redelivery after the database returns produces the side effect
  exactly once (idempotent guard). On the execution path, a database failure
  *before* the wire send leaves the broker untouched and resubmission of the
  same intent produces a single trade.
- **FalkorDB outage** — memory retrieval failure is contained (audited, bundle
  flows with ``memory=None``) and the next cycle recovers; lesson ingest
  failure never loses the canonical postmortem record.
- **MinIO outage** — artifact write failure is audited; the canonical review is
  still persisted and the postmortem completes; redelivery is idempotent.
- **LLM timeout / TradingAgents crash** — contained at the research boundary,
  never touches account or venue state, and the pipeline recovers when the
  boundary heals.

These run anywhere (no docker). Real container restarts live in
``test_live_infra_restart.py`` (``OT_CHAOS_LIVE=1``).
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from adapters.graphiti.memory import Memory
from adapters.graphiti.store import InMemoryStore
from adapters.tradingagents.errors import (
    TradingAgentsTimeoutError,
    TradingAgentsUnavailableError,
)
from adapters.tradingagents.mock import MockTradingAgentsAdapter
from adapters.tradingagents.schemas import MockScenario, TradingAgentsRating
from apps.worker.bus import BusUnavailableError, RedisStreamBus
from apps.worker.pipeline import StageWorker
from core.clock.clocks import VirtualClock
from core.config.settings import get_settings
from core.domain.enums import OrderState, PipelineStatus
from core.events.envelope import build_domain_event
from core.schemas.events import DomainEvent
from engines.posttrade.artifacts import MemoryArtifactStore
from sqlalchemy.exc import OperationalError

from chaos_faults import (
    GuardedProbeStage,
    ScriptedRedis,
    SwitchableTradingAgentsAdapter,
    TransientOutage,
)
from execution_helpers import (
    FakeReconcileClient,
    Stack,
    make_ack,
    make_fill_event,
    make_intent,
    make_position_snapshot_event,
)
from factories import make_market_snapshot, make_memory_episode
from worker_helpers import PaperStack, build_paper_stack, scripted_snapshots

NOW = datetime(2026, 8, 27, tzinfo=UTC)


def _snapshot_event(clock: VirtualClock) -> DomainEvent:
    payload = make_market_snapshot(clock.now(), source="chaos-infra")
    return build_domain_event(
        event_name="market.snapshot.created",
        payload=payload,
        clock=clock,
        producer="chaos-tests",
        trace_id=uuid4(),
    )


def _long_adapter(clock: VirtualClock) -> MockTradingAgentsAdapter:
    return MockTradingAgentsAdapter(
        scenarios={
            "EURUSD": MockScenario(
                scenario_id="long-eurusd",
                decision_markdown="**Rating**: Buy",
                rating=TradingAgentsRating.BUY,
            )
        },
        clock_now=clock.now,
    )


def _two_cycle_source() -> scripted_snapshots:
    return scripted_snapshots(
        {"EURUSD": [Decimal("1.10000"), Decimal("1.09700")]}
    )


def _run_two_cycles(stack: PaperStack) -> list[DomainEvent]:
    events: list[DomainEvent] = []
    events.extend(stack.runner.run_once())
    stack.clock.advance(timedelta(minutes=5))
    events.extend(stack.runner.run_once())
    return events


# ── Redis termination ────────────────────────────────────────────────────────


def _redis_bus(scripted: ScriptedRedis, **overrides: object) -> RedisStreamBus:
    kwargs: dict[str, object] = {
        "stream_key": "opentrading:events",
        "connection_factory": lambda url: scripted,
        "retry_base_seconds": 0.001,
        "retry_max_seconds": 0.004,
    }
    kwargs.update(overrides)
    return RedisStreamBus("redis://127.0.0.1:6379/0", **kwargs)  # type: ignore[arg-type]


class TestRedisTermination:
    def test_producer_retries_through_termination_without_losing_events(self) -> None:
        scripted = ScriptedRedis()
        bus = _redis_bus(scripted)
        clock = VirtualClock(NOW)
        first = _snapshot_event(clock)
        bus.publish(first)
        assert scripted.xlen("opentrading:events") == 1

        # Terminate Redis: publish keeps retrying unattended (never raises,
        # never half-writes), then resumes exactly once when Redis returns.
        scripted.terminate()
        results: dict[str, object] = {}
        second = _snapshot_event(clock)

        def publish_while_down() -> None:
            results["id"] = bus.publish(second)

        thread = threading.Thread(target=publish_while_down)
        thread.start()
        time.sleep(0.05)
        assert thread.is_alive(), "unattended publish must retry while Redis is down"
        scripted.restore()
        thread.join(timeout=2.0)
        assert not thread.is_alive()
        assert results["id"] == "2-0"

        # Both messages were queued exactly once and are delivered exactly once.
        assert scripted.xlen("opentrading:events") == 2
        bus.ensure_group("workers:fusion")
        delivered = bus.read_new("workers:fusion", "w-1", count=10, block_ms=0)
        assert [m.message_id for m in delivered] == ["1-0", "2-0"]
        for message in delivered:
            bus.ack("workers:fusion", message.message_id)
        assert bus.read_new("workers:fusion", "w-1", count=10, block_ms=0) == []
        assert bus.pending("workers:fusion") == []

    def test_bounded_bus_raises_clean_error_while_redis_is_down(self) -> None:
        scripted = ScriptedRedis()
        bus = _redis_bus(scripted, max_attempts=2)
        scripted.terminate()
        clock = VirtualClock(NOW)
        with pytest.raises(BusUnavailableError):
            bus.publish(_snapshot_event(clock))
        scripted.restore()
        assert scripted.xlen("opentrading:events") == 0  # nothing half-written


# ── PostgreSQL restart ───────────────────────────────────────────────────────


class TestPostgresRestart:
    def test_store_outage_mid_stage_redelivers_and_never_duplicates(self) -> None:
        clock = VirtualClock(NOW)
        stack = build_paper_stack(
            clock=clock, settings=get_settings(), source=scripted_snapshots()
        )
        outage = TransientOutage(
            stack.store, fail_methods={"save_context_fragment"}, failures=1
        )
        stack.rt.store = outage  # type: ignore[assignment]
        probe = GuardedProbeStage()
        worker = StageWorker(
            group="ot:fusion",
            consumer="worker-1",
            stages=[probe],
            rt=stack.rt,
            bus=stack.bus,
            clock=clock,
        )
        worker.start()
        event = _snapshot_event(clock)
        stack.bus.publish(event)

        # The database dies mid-stage: the side-effect write fails, the message
        # is left unacked, and no partial state is visible.
        worker.run_iteration()
        assert probe.calls == 1
        assert len(stack.bus.pending("ot:fusion")) == 1
        assert stack.store.get_context(event.trace_id) is None  # no partial state
        run = stack.store.get_run(event.trace_id, probe.name)
        assert run is not None and run.status is PipelineStatus.FAILED

        # PostgreSQL returns; the restart redelivery produces exactly-once.
        outage.recover()
        clock.advance(
            timedelta(milliseconds=stack.config.bus.claim_idle_ms + 100)
        )
        worker.run_iteration()
        assert probe.calls == 2
        assert stack.bus.pending("ot:fusion") == []
        context = stack.store.get_context(event.trace_id)
        assert context is not None
        assert context.fragments["probe"]["produced"] is True
        assert context.fragments["probe"]["attempt"] == 2  # one side effect, not two
        run = stack.store.get_run(event.trace_id, probe.name)
        assert run is not None
        assert run.status is PipelineStatus.SUCCEEDED
        assert run.attempt == 2

        # A further redelivery is a no-op: the idempotency guard holds.
        worker.handle_message(
            type("Msg", (), {"message_id": "x-0", "delivery_count": 2, "event": event})()
        )
        assert probe.calls == 2

    def test_database_outage_blocks_send_and_resubmission_is_one_trade(self) -> None:
        from engines.execution.persistence import InMemoryExecutionStateStore

        store = InMemoryExecutionStateStore()
        outage = TransientOutage(store, fail_methods={"save_order"}, failures=1)
        stack = Stack(store=outage)  # type: ignore[arg-type]
        client = FakeReconcileClient()
        service = stack.service(client)
        intent = make_intent()

        # PostgreSQL goes down at the moment of the authoritative write.
        # Write-before-send: the broker must never see the order.
        with pytest.raises(OperationalError):
            service.submit(intent)
        assert client.submitted == []  # zero broker exposure
        assert store.get_order(intent.order_intent_id) is None  # no partial state

        # The database returns; the crash-recovery path resubmits the same
        # intent and produces exactly one trade.
        outage.recover()
        client.submit_reply = make_ack(intent.order_intent_id)
        client.events = [
            make_fill_event(stack.clock.now(), intent.order_intent_id),
            make_position_snapshot_event(
                stack.clock.now(), intent_id=intent.order_intent_id
            ),
        ]
        record = service.submit(intent)
        assert record.state is OrderState.FILLED
        assert record.filled_quantity == intent.quantity
        assert len(client.submitted) == 1  # the wire saw this intent exactly once
        assert len(store.list_orders()) == 1
        assert len(store.list_positions(open_only=True)) == 1
        assert store.get_safe_mode().active is False


# ── FalkorDB outage ──────────────────────────────────────────────────────────


class TestFalkordbOutage:
    def test_retrieval_outage_is_contained_then_recovers(self) -> None:
        clock = VirtualClock(NOW)
        raw = InMemoryStore()
        seeded = Memory(raw, clock=clock)
        seeded.ingest(
            make_memory_episode(
                clock.now(), content={"stance": "LONG", "instrument_id": "EURUSD"}
            ),
            source="test.seed",
            event_time=clock.now(),
            available_time=clock.now(),
            ingested_at=clock.now(),
        )
        outage = TransientOutage(raw, fail_methods={"search"}, failures=1)
        memory = Memory(outage, clock=clock)
        stack = build_paper_stack(
            clock=clock,
            settings=get_settings(),
            memory=memory,
            source=scripted_snapshots({"EURUSD": [Decimal("1.10000")]}),
        )

        # FalkorDB is down: retrieval fails, the cycle still completes.
        events = stack.runner.run_once()
        bundle = next(e for e in events if e.event_name == "research.bundle.created")
        assert bundle.payload.get("memory") is None
        assert any(
            entry.action == "memory.retrieval.failed" for entry in stack.audit_sink.entries
        )

        # FalkorDB returns: the next cycle sees the point-in-time memory again.
        outage.recover()
        stack.clock.advance(timedelta(minutes=5))
        recovered = stack.runner.run_once()
        recovered_bundle = next(
            e for e in recovered if e.event_name == "research.bundle.created"
        )
        assert recovered_bundle.payload.get("memory") is not None

    def test_ingest_outage_never_loses_the_canonical_postmortem(self) -> None:
        clock = VirtualClock(datetime(2026, 8, 27, tzinfo=UTC))
        raw = InMemoryStore()
        outage = TransientOutage(raw, fail_methods={"store"}, failures=1)
        memory = Memory(outage, clock=clock)
        stack = build_paper_stack(
            clock=clock,
            settings=get_settings(),
            tradingagents=_long_adapter(clock),
            memory=memory,
            source=_two_cycle_source(),
        )

        events = _run_two_cycles(stack)
        names = [e.event_name for e in events]
        assert "trade.closed" in names
        # The lesson sink fails but the postmortem itself is authoritative and
        # still completed and persisted with canonical metrics.
        assert "postmortem.completed" in names
        assert "memory.episode.created" not in names
        outcome = stack.ledger.outcomes()[0]
        review = stack.posttrade_store.get_by_trade(outcome.trade_id)
        assert review is not None
        assert review.postmortem_completed is True
        assert review.episode_id is None
        assert any(
            entry.action == "memory.ingest.failed" for entry in stack.audit_sink.entries
        )


# ── MinIO outage ─────────────────────────────────────────────────────────────


class TestMinioOutage:
    def test_artifact_outage_never_loses_the_review_and_redelivery_is_idempotent(
        self,
    ) -> None:
        from apps.worker.stages.posttrade import PosttradeStage

        clock = VirtualClock(datetime(2026, 8, 27, tzinfo=UTC))
        artifacts = MemoryArtifactStore()
        outage = TransientOutage(artifacts, fail_methods={"put_json"}, failures=1)
        stack = build_paper_stack(
            clock=clock,
            settings=get_settings(),
            tradingagents=_long_adapter(clock),
            artifact_store=outage,
            source=_two_cycle_source(),
        )

        events = _run_two_cycles(stack)
        names = [e.event_name for e in events]
        assert "trade.closed" in names
        # The artifact sink fails: audited, review still persisted, postmortem
        # still completed — the audit trail is authoritative, not the bucket.
        assert "postmortem.completed" in names
        outcome = stack.ledger.outcomes()[0]
        review = stack.posttrade_store.get_by_trade(outcome.trade_id)
        assert review is not None
        assert review.postmortem_completed is True
        assert review.artifact_key is None
        assert any(
            entry.action == "posttrade.artifact.failed"
            for entry in stack.audit_sink.entries
        )

        # Redelivery of the closing event (worker restart) is idempotent: the
        # stage gate sees the SUCCEEDED run record and does nothing at all.
        closed = next(e for e in events if e.event_name == "trade.closed")
        replayed = PosttradeStage().handle(stack.rt, closed)
        assert replayed == []  # no reprocessing, no duplicate postmortem
        assert stack.posttrade_store.get_by_trade(outcome.trade_id) == review


# ── LLM timeout / TradingAgents crash ────────────────────────────────────────


class TestLlmBoundaryFailures:
    def test_llm_timeout_is_contained_and_the_cycle_recovers(self) -> None:
        clock = VirtualClock(NOW)
        adapter = SwitchableTradingAgentsAdapter(
            _long_adapter(clock),
            error=TradingAgentsTimeoutError,
            clock_now=clock.now,
        )
        adapter.fail = True
        stack = build_paper_stack(
            clock=clock,
            settings=get_settings(),
            tradingagents=adapter,
            source=scripted_snapshots({"EURUSD": [Decimal("1.10000")]}),
        )

        events = stack.runner.run_once()
        bundle = next(e for e in events if e.event_name == "research.bundle.created")
        assert bundle.payload["llm"] is None
        assert "TradingAgentsTimeoutError" in bundle.payload["llm_error"]
        assert any(
            entry.action == "llm.analysis.failed" for entry in stack.audit_sink.entries
        )
        account = stack.store.get_account(stack.config.account_id)
        assert account is not None  # account state intact

        # The LLM returns: the next cycle produces a signal again.
        adapter.fail = False
        stack.clock.advance(timedelta(minutes=5))
        recovered = stack.runner.run_once()
        recovered_bundle = next(
            e for e in recovered if e.event_name == "research.bundle.created"
        )
        assert recovered_bundle.payload["llm"] is not None
        assert "llm.signal.created" in [e.event_name for e in recovered]

    def test_tradingagents_crash_never_reaches_the_venue_and_recovers(self) -> None:
        clock = VirtualClock(NOW)
        adapter = SwitchableTradingAgentsAdapter(
            _long_adapter(clock),
            error=TradingAgentsUnavailableError,
            clock_now=clock.now,
        )
        adapter.fail = True
        stack = build_paper_stack(
            clock=clock,
            settings=get_settings(),
            tradingagents=adapter,
            source=scripted_snapshots({"EURUSD": [Decimal("1.10000")]}),
            config_overrides={"llm_required": True},
        )

        # TradingAgents crashed and llm_required: the cycle is skipped cleanly —
        # no proposal, no order, no account change.
        events = stack.runner.run_once()
        assert all(e.event_name != "trade.proposal.created" for e in events)
        assert stack.execution_store.list_orders() == ()
        account = stack.store.get_account(stack.config.account_id)
        assert account is not None and account.version == 1

        # TradingAgents is healthy again: the pipeline resumes end to end.
        adapter.fail = False
        stack.clock.advance(timedelta(minutes=5))
        recovered = stack.runner.run_once()
        assert "trade.proposal.created" in [e.event_name for e in recovered]
        assert stack.execution_store.list_orders()
