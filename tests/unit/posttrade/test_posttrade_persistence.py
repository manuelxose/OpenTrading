"""Round-trip coverage for the canonical post-trade persistence mapping."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from core.domain.enums import SignalDirection
from core.schemas.posttrade import PostTradeReviewRecord
from engines.posttrade.persistence import _review_from_row, _review_values

from factories import make_posttrade_review, make_trade_metrics


class _Row:
    def __init__(self, values: dict[str, object]) -> None:
        self.__dict__.update(values)


def test_database_mapping_preserves_every_trade_metric() -> None:
    now = datetime(2026, 8, 27, tzinfo=UTC)
    review = make_posttrade_review(now)
    record = PostTradeReviewRecord(
        review_id=review.review_id,
        trade_id=review.trade_id,
        instrument_id="EURUSD",
        strategy_id="strategy-01",
        strategy_version="3.1.0",
        direction=SignalDirection.LONG,
        opened_at=now,
        closed_at=now,
        exit_reason="take_profit",
        metrics=make_trade_metrics(now),
        verdict="SUPPORTED",
        postmortem_completed=True,
        review_payload=review.canonical_dict(),
        trace_id=uuid4(),
        created_at=now,
    )

    restored = _review_from_row(_Row(_review_values(record)))

    assert restored.metrics == record.metrics
