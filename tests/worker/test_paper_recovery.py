"""Recovery tests: worker restart, poisoning, LLM/model failures, mode guard."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from adapters.tradingagents.mock import MockTradingAgentsAdapter
from apps.worker.persistence import _retry
from apps.worker.pipeline import StageWorker
from apps.worker.stages.base import Stage, StageRuntime
from core.clock.clocks import VirtualClock
from core.config.settings import get_settings
from core.domain.enums import OrderState, PipelineStageName, PipelineStatus
from core.schemas.events import DomainEvent

from worker_helpers import build_paper_stack, scripted_snapshots

NOW = datetime(2026, 8, 27, tzinfo=UTC)


class _ProbeStage(Stage):
    """Stage that records attempts and can be told to fail N times."""

    name = PipelineStageName.FUSION
    consumes = ("market.snapshot.created",)

    def __init__(self) -> None:
        self.calls = 0
        self.fail_times = 0

    def process(self, rt: StageRuntime, event: DomainEvent) -> list[DomainEvent]:
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("injected stage failure")
        return []


def make_runtime(clock: VirtualClock):
    stack = build_paper_stack(
        clock=clock,
        settings=get_settings(),
        source=scripted_snapshots(),
    )
    return stack


class TestWorkerRestartRecovery:
    def test_failed_message_is_redelivered_and_idempotent(self) -> None:
        clock = VirtualClock(NOW)
        stack = make_runtime(clock)
        probe = _ProbeStage()
        probe.fail_times = 1
        worker = StageWorker(
            group="ot:fusion",
            consumer="worker-1",
            stages=[probe],
            rt=stack.rt,
            bus=stack.bus,
            clock=clock,
        )
        worker.start()
        # publish a snapshot event (probe consumes it)
        event = _snapshot_event(clock)
        stack.bus.publish(event)

        worker.run_iteration()  # delivers → probe raises → left unacked
        assert probe.calls == 1
        assert len(stack.bus.pending("ot:fusion")) == 1
        # the failed attempt is recorded
        run_record = stack.store.get_run(event.trace_id, probe.name)
        assert run_record is not None
        assert run_record.status is PipelineStatus.FAILED

        # worker restarts: reclaim the stale PEL entry after the idle window
        clock.advance(timedelta(seconds=10))
        worker.run_iteration()
        assert probe.calls == 2
        assert stack.bus.pending("ot:fusion") == []

        # a third delivery (crash after ack? not possible — simulate by direct
        # handle) is a no-op because the stage already succeeded
        message = type(
            "Msg",
            (),
            {"message_id": "x-0", "delivery_count": 1, "event": event},
        )()
        worker.handle_message(message)  # type: ignore[arg-type]
        assert probe.calls == 2  # no reprocessing

    def test_poisoned_message_is_dead_lettered(self) -> None:
        clock = VirtualClock(NOW)
        stack = make_runtime(clock)
        probe = _ProbeStage()
        probe.fail_times = 1000
        max_deliveries = stack.config.bus.max_deliveries
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
        # delivery 1 comes from read_new; each reclaim adds one delivery; the
        # dead-letter fires once the count exceeds max_deliveries.
        for _ in range(max_deliveries + 2):
            worker.run_iteration()
            clock.advance(timedelta(seconds=10))
        assert stack.bus.pending("ot:fusion") == []
        assert len(stack.bus.dead.get("ot:fusion", [])) == 1
        archived = stack.bus.dead["ot:fusion"][0]
        assert "exceeded 5 deliveries" in archived[2]


class TestLlmFailureContainment:
    def test_tradingagents_failure_never_breaks_account_state(self) -> None:
        clock = VirtualClock(NOW)
        adapter = MockTradingAgentsAdapter(fail_for={"EURUSD"}, clock_now=clock.now)
        stack = build_paper_stack(
            clock=clock,
            settings=get_settings(),
            tradingagents=adapter,
            source=scripted_snapshots(),
        )
        events = stack.runner.run_once()
        bundle = next(e for e in events if e.event_name == "research.bundle.created")
        assert bundle.payload["llm"] is None
        assert bundle.payload["llm_error"]  # contained, not propagated
        account = stack.store.get_account(stack.config.account_id)
        assert account is not None
        assert account.realized_pnl == Decimal("0")  # untouched by LLM failure
        assert any(entry.action == "llm.analysis.failed" for entry in stack.audit_sink.entries)

    def test_llm_required_skips_the_cycle_cleanly(self) -> None:
        clock = VirtualClock(NOW)
        adapter = MockTradingAgentsAdapter(fail_for={"EURUSD"}, clock_now=clock.now)
        stack = build_paper_stack(
            clock=clock,
            settings=get_settings(),
            tradingagents=adapter,
            source=scripted_snapshots(),
            config_overrides={"llm_required": True},
        )
        events = stack.runner.run_once()
        assert all(e.event_name != "trade.proposal.created" for e in events)
        account = stack.store.get_account(stack.config.account_id)
        assert account is not None
        assert account.version == 1  # account never updated


class TestNoRealBrokerExecution:
    def test_live_modes_are_refused_outright(self) -> None:
        from adapters.tradingagents.schemas import MockScenario, TradingAgentsRating
        from core.domain.enums import OperatingMode

        clock = VirtualClock(NOW)
        adapter = MockTradingAgentsAdapter(
            scenarios={
                "EURUSD": MockScenario(
                    scenario_id="long",
                    decision_markdown="**Rating**: Buy",
                    rating=TradingAgentsRating.BUY,
                )
            },
            clock_now=clock.now,
        )
        stack = build_paper_stack(
            clock=clock,
            settings=get_settings(),
            tradingagents=adapter,
            source=scripted_snapshots(),
            config_overrides={"operating_mode": OperatingMode.LIVE_GATED},
        )
        with pytest.raises(RuntimeError, match="no real broker execution"):
            stack.runner.run_once()
        # the guard fires before the venue call; no order ever filled
        orders = stack.execution_store.list_orders()
        assert all(order.state is not OrderState.FILLED for order in orders)


class TestDatabaseRetry:
    def test_retry_operation_recovers_from_transient_errors(self) -> None:
        from sqlalchemy.exc import OperationalError

        calls = {"n": 0}

        def flaky() -> str:
            calls["n"] += 1
            if calls["n"] <= 2:
                raise OperationalError("SELECT 1", {}, Exception("conn reset"))
            return "ok"

        assert _retry(flaky, name="probe", base=0.001, cap=0.01) == "ok"
        assert calls["n"] == 3

    def test_retry_gives_up_after_attempts(self) -> None:
        from sqlalchemy.exc import OperationalError

        def always() -> str:
            raise OperationalError("SELECT 1", {}, Exception("down"))

        with pytest.raises(OperationalError):
            _retry(always, name="probe", base=0.001, cap=0.01, attempts=3)


def _snapshot_event(clock: VirtualClock) -> DomainEvent:
    from core.events.envelope import build_domain_event

    from factories import make_market_snapshot

    payload = make_market_snapshot(clock.now(), source="recovery-tests")
    return build_domain_event(
        event_name="market.snapshot.created",
        payload=payload,
        clock=clock,
        producer="recovery-tests",
        trace_id=uuid4(),
    )
