"""Pipeline store tests: idempotent run ledger, CAS lifecycles, account CAS."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from apps.worker.persistence import InMemoryPipelineStore, StalePipelineStateError
from core.domain.enums import (
    PipelineStageName,
    PipelineStatus,
    SignalDirection,
    TradeLifecycleState,
)
from core.schemas.pipeline import PaperAccountRecord, PipelineRunRecord, TradeLifecycle

NOW = datetime(2026, 8, 27, tzinfo=UTC)


def make_run(
    trace_id: UUID, stage: PipelineStageName, status: PipelineStatus, attempt: int = 1
) -> PipelineRunRecord:
    return PipelineRunRecord(
        run_id=uuid4(),
        trace_id=trace_id,
        cycle_id="cycle-1",
        instrument_id="EURUSD",
        stage=stage,
        status=status,
        attempt=attempt,
        started_at=NOW,
        completed_at=NOW if status is not PipelineStatus.RUNNING else None,
    )


def make_lifecycle(trace_id: UUID, state: TradeLifecycleState) -> TradeLifecycle:
    return TradeLifecycle(
        lifecycle_id=uuid4(),
        trace_id=trace_id,
        strategy_id="paper-baseline-001",
        strategy_version="1.0.0",
        instrument_id="EURUSD",
        state=state,
        version=1,
        created_at=NOW,
        updated_at=NOW,
    )


def make_account(version: int = 1) -> PaperAccountRecord:
    return PaperAccountRecord(
        account_id="paper-account-001",
        currency="USD",
        balance=Decimal("100000"),
        equity=Decimal("100000"),
        realized_pnl=Decimal("0"),
        daily_pnl=Decimal("0"),
        peak_equity=Decimal("100000"),
        consecutive_losses=0,
        last_loss_at=None,
        open_positions=0,
        version=version,
        updated_at=NOW,
    )


class TestPipelineRunLedger:
    def test_save_run_is_idempotent_on_success(self) -> None:
        store = InMemoryPipelineStore()
        trace_id = uuid4()
        first = store.save_run(
            make_run(trace_id, PipelineStageName.RESEARCH, PipelineStatus.SUCCEEDED)
        )
        second = store.save_run(
            make_run(trace_id, PipelineStageName.RESEARCH, PipelineStatus.RUNNING, attempt=2)
        )
        assert second == first
        assert second.status is PipelineStatus.SUCCEEDED  # terminal result immutable

    def test_failed_run_is_replaced_on_retry(self) -> None:
        store = InMemoryPipelineStore()
        trace_id = uuid4()
        store.save_run(make_run(trace_id, PipelineStageName.RESEARCH, PipelineStatus.FAILED))
        retry = store.save_run(
            make_run(trace_id, PipelineStageName.RESEARCH, PipelineStatus.SUCCEEDED, attempt=2)
        )
        assert retry.status is PipelineStatus.SUCCEEDED
        assert retry.attempt == 2

    def test_has_succeeded_and_runs_for_trace(self) -> None:
        store = InMemoryPipelineStore()
        trace_id = uuid4()
        assert not store.has_succeeded(trace_id, PipelineStageName.RESEARCH)
        store.save_run(make_run(trace_id, PipelineStageName.RESEARCH, PipelineStatus.SUCCEEDED))
        assert store.has_succeeded(trace_id, PipelineStageName.RESEARCH)
        assert not store.has_succeeded(trace_id, PipelineStageName.FUSION)
        assert len(store.runs_for_trace(trace_id)) == 1


class TestLifecycleCAS:
    def test_update_with_cas(self) -> None:
        store = InMemoryPipelineStore()
        lifecycle = store.save_lifecycle(make_lifecycle(uuid4(), TradeLifecycleState.RESEARCHING))
        updated = lifecycle.model_copy(
            update={"state": TradeLifecycleState.SIGNAL_FUSED, "version": 2, "updated_at": NOW}
        )
        result = store.update_lifecycle(updated, expected_version=1)
        assert result.state is TradeLifecycleState.SIGNAL_FUSED
        assert result.version == 2

    def test_stale_update_raises(self) -> None:
        store = InMemoryPipelineStore()
        lifecycle = store.save_lifecycle(make_lifecycle(uuid4(), TradeLifecycleState.RESEARCHING))
        updated = lifecycle.model_copy(
            update={"state": TradeLifecycleState.SIGNAL_FUSED, "version": 2, "updated_at": NOW}
        )
        store.update_lifecycle(updated, expected_version=1)
        with pytest.raises(StalePipelineStateError):
            store.update_lifecycle(updated, expected_version=1)  # replay of old write

    def test_lookup_by_proposal_order_trace(self) -> None:
        store = InMemoryPipelineStore()
        trace_id = uuid4()
        proposal_id = uuid4()
        order_id = uuid4()
        store.save_lifecycle(
            TradeLifecycle(
                lifecycle_id=uuid4(),
                trace_id=trace_id,
                proposal_id=proposal_id,
                strategy_id="s",
                strategy_version="1",
                instrument_id="EURUSD",
                state=TradeLifecycleState.ORDER_CREATED,
                direction=SignalDirection.LONG,
                order_intent_id=order_id,
                stop_loss=Decimal("1.0900"),
                take_profit=Decimal("1.1200"),
                version=1,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        assert store.get_lifecycle_by_proposal(proposal_id) is not None
        assert store.get_lifecycle_by_order(order_id) is not None
        assert store.get_lifecycle_by_trace(trace_id) is not None


class TestPaperAccount:
    def test_upsert_new_and_cas_update(self) -> None:
        store = InMemoryPipelineStore()
        created = store.upsert_account(make_account(version=1), expected_version=None)
        assert created.version == 1
        updated = created.model_copy(
            update={"realized_pnl": Decimal("-5"), "version": 2, "updated_at": NOW}
        )
        result = store.upsert_account(updated, expected_version=1)
        assert result.realized_pnl == Decimal("-5")
        assert result.version == 2

    def test_stale_account_update_raises(self) -> None:
        store = InMemoryPipelineStore()
        created = store.upsert_account(make_account(version=1), expected_version=None)
        first = created.model_copy(
            update={"realized_pnl": Decimal("-5"), "version": 2, "updated_at": NOW}
        )
        store.upsert_account(first, expected_version=1)
        # replaying the old write against the now-updated record is stale
        with pytest.raises(StalePipelineStateError):
            store.upsert_account(first, expected_version=1)
