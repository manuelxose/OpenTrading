"""Post-trade artifacts: deterministic keys and the immutable audit payload."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

from core.domain.enums import SignalDirection
from core.schemas.posttrade import PostTradeReviewRecord
from engines.posttrade.artifacts import MemoryArtifactStore, artifact_key, build_artifact

from factories import make_posttrade_review, make_trade_metrics

REVIEW_ID = UUID("12345678-1234-4234-8234-123456789abc")


def make_record() -> PostTradeReviewRecord:
    now = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
    review = make_posttrade_review(now)
    return PostTradeReviewRecord(
        review_id=REVIEW_ID,
        trade_id=review.trade_id,
        instrument_id="EURUSD",
        strategy_id="paper-baseline-001",
        strategy_version="1.0.0",
        direction=SignalDirection.LONG,
        opened_at=now,
        closed_at=now,
        exit_reason="take_profit",
        metrics=make_trade_metrics(now),
        verdict="SUPPORTED",
        postmortem_completed=True,
        review_payload=review.canonical_dict(),
        created_at=now,
    )


def test_artifact_key_layout() -> None:
    closed_at = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)
    assert artifact_key(closed_at, REVIEW_ID) == (f"reviews/2026/08/{REVIEW_ID}.json")


def test_build_artifact_is_json_serializable_and_complete() -> None:
    record = make_record()
    artifact = build_artifact(
        record,
        context_fragments={"quant": {"signal_id": "s-1"}},
        price_path=[
            {
                "ts": "2026-08-27T10:00:00+00:00",
                "high": "1.08",
                "low": "1.07",
                "close": "1.075",
            }
        ],
    )
    assert artifact["artifact_schema"] == "opentrading.posttrade.artifact"
    assert artifact["review"] == record.review_payload
    assert artifact["metrics"]["pnl_net"] == "48.00"
    assert artifact["trade_context"]["quant"]["signal_id"] == "s-1"
    assert artifact["price_path"] == [
        {"ts": "2026-08-27T10:00:00+00:00", "high": "1.08", "low": "1.07", "close": "1.075"}
    ]
    json.dumps(artifact)  # lossless JSON


def test_memory_store_round_trip() -> None:
    store = MemoryArtifactStore()
    store.put_json("reviews/2026/08/x.json", {"a": 1})
    assert store.exists("reviews/2026/08/x.json")
    assert store.get_json("reviews/2026/08/x.json") == {"a": 1}
    assert not store.exists("reviews/2026/08/y.json")
