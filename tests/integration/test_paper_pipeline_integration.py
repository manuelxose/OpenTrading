"""Integration tests: autonomous paper pipeline against real Redis + PostgreSQL.

Requires ``make up`` and ``OT_INTEGRATION=1`` — otherwise skipped, like the
other integration suites. Verifies:

- the RedisStreamBus round trip through a consumer group, PEL reclaim and
  dead-lettering against a real Redis server;
- the PostgresPipelineStore CRUD + CAS against real PostgreSQL.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from apps.worker.bus import RedisStreamBus
from apps.worker.persistence import PostgresPipelineStore, StalePipelineStateError
from core.clock.clocks import SystemClock
from core.config.settings import get_settings
from core.domain.enums import (
    PipelineStageName,
    PipelineStatus,
    TradeLifecycleState,
)
from core.events.envelope import build_domain_event
from core.schemas.pipeline import (
    PaperAccountRecord,
    PipelineRunRecord,
    TradeLifecycle,
)

from factories import make_market_snapshot

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("OT_INTEGRATION"),
        reason="local stack not running (make up)",
    ),
]

NOW = datetime(2026, 8, 27, tzinfo=UTC)


@pytest.fixture()
def store() -> PostgresPipelineStore:
    return PostgresPipelineStore(get_settings().postgres_dsn)


@pytest.fixture()
def bus() -> RedisStreamBus:
    settings = get_settings()
    return RedisStreamBus(
        settings.redis_url,
        stream_key=f"test:pipeline:{uuid4().hex[:8]}",
        retry_base_seconds=0.05,
        retry_max_seconds=0.2,
        max_attempts=3,
        clock=SystemClock(),
    )


class TestRedisBusIntegration:
    def test_publish_read_ack_claim_cycle(self, bus: RedisStreamBus) -> None:
        event = _snapshot_event()
        bus.ensure_group("g1")
        message_id = bus.publish(event)
        messages = bus.read_new("g1", "c1", count=5, block_ms=100)
        assert [m.message_id for m in messages] == [message_id]
        assert messages[0].event.trace_id == event.trace_id
        # pending until acked
        assert [p.message_id for p in bus.pending("g1")] == [message_id]
        bus.ack("g1", message_id)
        assert bus.pending("g1") == []
        # reclaim of an unacked entry (restart recovery)
        message_id = bus.publish(_snapshot_event())
        bus.read_new("g1", "c1", count=5, block_ms=100)
        claimed = bus.claim_stale("g1", "c1-restarted", min_idle_ms=0, count=5)
        assert [m.message_id for m in claimed] == [message_id]
        bus.ack("g1", message_id)

    def test_dead_letter_archives(self, bus: RedisStreamBus) -> None:
        bus.ensure_group("g2")
        bus.publish(_snapshot_event())
        message = bus.read_new("g2", "c1", count=1, block_ms=100)[0]
        bus.dead_letter("g2", message, "poisoned-by-test")
        assert bus.pending("g2") == []


class TestPostgresPipelineStoreIntegration:
    def test_run_ledger_idempotency(self, store: PostgresPipelineStore) -> None:
        trace_id = uuid4()
        record = PipelineRunRecord(
            run_id=uuid4(),
            trace_id=trace_id,
            cycle_id="integration",
            instrument_id="EURUSD",
            stage=PipelineStageName.RESEARCH,
            status=PipelineStatus.SUCCEEDED,
            attempt=1,
            started_at=NOW,
            completed_at=NOW,
        )
        saved = store.save_run(record)
        duplicate = store.save_run(record.model_copy(update={"run_id": uuid4()}))
        assert duplicate.run_id == saved.run_id  # terminal rows are immutable
        assert store.has_succeeded(trace_id, PipelineStageName.RESEARCH)

    def test_lifecycle_cas(self, store: PostgresPipelineStore) -> None:
        trace_id = uuid4()
        lifecycle = store.save_lifecycle(
            TradeLifecycle(
                lifecycle_id=uuid4(),
                trace_id=trace_id,
                strategy_id="s",
                strategy_version="1",
                instrument_id="EURUSD",
                state=TradeLifecycleState.RESEARCHING,
                version=1,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        updated = lifecycle.model_copy(
            update={
                "state": TradeLifecycleState.SIGNAL_FUSED,
                "version": 2,
                "updated_at": NOW,
            }
        )
        assert store.update_lifecycle(updated, expected_version=1).version == 2
        with pytest.raises(StalePipelineStateError):
            store.update_lifecycle(updated, expected_version=1)

    def test_account_cas(self, store: PostgresPipelineStore) -> None:
        account_id = f"test-{uuid4().hex[:8]}"
        created = store.upsert_account(
            PaperAccountRecord(
                account_id=account_id,
                currency="USD",
                balance=Decimal("100000"),
                equity=Decimal("100000"),
                realized_pnl=Decimal("0"),
                daily_pnl=Decimal("0"),
                peak_equity=Decimal("100000"),
                consecutive_losses=0,
                open_positions=0,
                version=1,
                updated_at=NOW,
            ),
            expected_version=None,
        )
        updated = created.model_copy(
            update={
                "realized_pnl": Decimal("-5"),
                "balance": Decimal("99995"),
                "version": 2,
                "updated_at": NOW,
            }
        )
        result = store.upsert_account(updated, expected_version=1)
        assert result.realized_pnl == Decimal("-5")
        assert store.get_account(account_id) is not None


def _snapshot_event():
    payload = make_market_snapshot(NOW, source="integration")
    return build_domain_event(
        event_name="market.snapshot.created",
        payload=payload,
        clock=SystemClock(),
        producer="integration",
        trace_id=uuid4(),
        event_time=NOW,
        ingested_at=NOW,
    )
