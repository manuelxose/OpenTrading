"""Integration tests: post-trade stores against real PostgreSQL (+ MinIO).

Requires ``make up`` and ``OT_INTEGRATION=1`` — otherwise skipped. Verifies:

- ``PostgresPostTradeStore`` round-trip + idempotency against real PostgreSQL
  (migration 0005 tables);
- ``PostgresPipelineStore`` trade-context capture round-trip;
- ``MinioArtifactStore`` write/read/exists against the local MinIO stack.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from apps.worker.persistence import PostgresPipelineStore
from core.config.settings import get_settings
from core.domain.enums import SignalDirection
from core.schemas.posttrade import PostTradeReviewRecord
from engines.posttrade.artifacts import MemoryArtifactStore, MinioArtifactStore, artifact_key
from engines.posttrade.persistence import PostgresPostTradeStore

from factories import make_posttrade_review, make_trade_metrics

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.environ.get("OT_INTEGRATION"),
        reason="local stack not running (make up)",
    ),
]

NOW = datetime(2026, 8, 27, tzinfo=UTC)
REVIEW_ID = UUID("12345678-1234-4234-8234-123456789abc")


def _record() -> PostTradeReviewRecord:
    review = make_posttrade_review(NOW)
    return PostTradeReviewRecord(
        review_id=REVIEW_ID,
        trade_id=review.trade_id,
        instrument_id="EURUSD",
        strategy_id="paper-baseline-001",
        strategy_version="1.0.0",
        direction=SignalDirection.LONG,
        opened_at=NOW,
        closed_at=NOW,
        exit_reason="take_profit",
        metrics=make_trade_metrics(NOW),
        verdict="SUPPORTED",
        postmortem_completed=True,
        review_payload=review.canonical_dict(),
        trace_id=uuid4(),
        created_at=NOW,
    )


class TestPostgresPostTradeStore:
    def test_save_get_and_idempotency(self) -> None:
        store = PostgresPostTradeStore(get_settings().postgres_dsn)
        record = _record()
        saved = store.save_review(record)
        assert saved.review_id == REVIEW_ID

        restored = store.get_review(REVIEW_ID)
        assert restored is not None
        assert restored.metrics == record.metrics
        assert store.get_by_trade(record.trade_id) is not None
        assert store.has_review(record.trade_id)

        # Redelivery: the same review id returns the stored row unchanged.
        second = _record()
        assert store.save_review(second).review_id == REVIEW_ID
        assert len([r for r in store.list_reviews() if r.review_id == REVIEW_ID]) == 1


class TestPostgresTradeContext:
    def test_fragment_capture_and_retrieval(self) -> None:
        store = PostgresPipelineStore(get_settings().postgres_dsn)
        trace_id = uuid4()
        store.save_context_fragment(
            trace_id,
            "quant",
            {"signal_id": "s-1", "direction": "LONG"},
            instrument_id="EURUSD",
            updated_at=NOW,
        )
        store.save_context_fragment(
            trace_id,
            "proposal",
            {"proposal_id": "p-1"},
            instrument_id="EURUSD",
            updated_at=NOW,
        )
        context = store.get_context(trace_id)
        assert context is not None
        assert set(context.fragments) == {"quant", "proposal"}
        assert context.instrument_id == "EURUSD"


class TestMinioArtifacts:
    def test_put_get_exists(self) -> None:
        settings = get_settings()
        store = MinioArtifactStore(
            settings.minio_endpoint,
            settings.minio_access_key,
            settings.minio_secret_key,
            bucket=settings.posttrade_artifact_bucket,
            secure=settings.minio_secure,
        )
        key = artifact_key(NOW, REVIEW_ID)
        store.put_json(
            key,
            {"review_id": str(REVIEW_ID), "schema": "opentrading.posttrade.artifact"},
        )
        assert store.exists(key)
        assert store.get_json(key)["review_id"] == str(REVIEW_ID)


def test_memory_artifact_store_mirrors_minio_protocol() -> None:
    # Protocol parity: both implementations satisfy the same boundary.
    store: MemoryArtifactStore = MemoryArtifactStore()
    store.put_json("k", {"a": 1})
    assert store.get_json("k") == {"a": 1}
    assert store.exists("k")
