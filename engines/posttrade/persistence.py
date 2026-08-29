"""Post-trade review persistence: canonical metrics in PostgreSQL (INV-10).

One ``posttrade_reviews`` row per closed-and-reconciled trade. The row carries
every canonical metric as a typed, queryable column (PnL, fees, slippage,
R multiple, alpha, MAE/MFE, holding time, efficiencies, prediction error,
regime) plus the full ``PostTradeReview`` payload as JSONB for reconstruction.

Idempotency: ``save_review`` is keyed by ``review_id`` (deterministic UUIDv5
over the trade id) — a redelivered postmortem returns the stored row unchanged.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, Protocol
from uuid import UUID

from core.config.settings import ensure_psycopg_dsn
from core.schemas.posttrade import PostTradeReviewRecord
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Engine,
    Float,
    Integer,
    MetaData,
    Numeric,
    Table,
    Text,
    Uuid,
    create_engine,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import OperationalError

__all__ = [
    "InMemoryPostTradeStore",
    "PostTradeStore",
    "PostgresPostTradeStore",
    "posttrade_reviews_table",
]

logger = logging.getLogger(__name__)

_RETRYABLE = (OperationalError,)

metadata = MetaData()

posttrade_reviews_table = Table(
    "posttrade_reviews",
    metadata,
    Column("review_id", Uuid, primary_key=True),
    Column("trade_id", Uuid, nullable=False),
    Column("position_id", Text, nullable=True),
    Column("instrument_id", Text, nullable=False),
    Column("strategy_id", Text, nullable=False),
    Column("strategy_version", Text, nullable=False),
    Column("direction", Text, nullable=False),
    Column("opened_at", DateTime(timezone=True), nullable=False),
    Column("closed_at", DateTime(timezone=True), nullable=False),
    Column("exit_reason", Text, nullable=False),
    Column("pnl_gross", Numeric(38, 8), nullable=False),
    Column("pnl_net", Numeric(38, 8), nullable=False),
    Column("fees", Numeric(38, 8), nullable=False),
    Column("slippage", Numeric(38, 8), nullable=False),
    Column("r_multiple", Float, nullable=True),
    Column("alpha_pct", Float, nullable=True),
    Column("mae_pct", Float, nullable=True),
    Column("mfe_pct", Float, nullable=True),
    Column("holding_seconds", Integer, nullable=False),
    Column("entry_efficiency", Float, nullable=True),
    Column("exit_efficiency", Float, nullable=True),
    Column("prediction_error_pct", Float, nullable=True),
    Column("signal_calibration_error", JSONB, nullable=True),
    Column("expected_return_pct", Float, nullable=True),
    Column("actual_return_pct", Float, nullable=True),
    Column("benchmark_return_pct", Float, nullable=True),
    Column("expected_r", Float, nullable=True),
    Column("market_regime", Text, nullable=False),
    Column("verdict", Text, nullable=False),
    Column("postmortem_completed", Boolean, nullable=False),
    Column("review_payload", JSONB, nullable=False),
    Column("artifact_key", Text, nullable=True),
    Column("vault_path", Text, nullable=True),
    Column("episode_id", Uuid, nullable=True),
    Column("trace_id", Uuid, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("schema_version", Text, nullable=False),
)


class PostTradeStore(Protocol):
    """Canonical postmortem persistence boundary (PostgreSQL, INV-10)."""

    def save_review(self, record: PostTradeReviewRecord) -> PostTradeReviewRecord:
        """Insert one review. Idempotent per review_id: a second insert for an
        existing id returns the stored record unchanged."""
        ...

    def get_review(self, review_id: UUID) -> PostTradeReviewRecord | None: ...
    def get_by_trade(self, trade_id: UUID) -> PostTradeReviewRecord | None: ...
    def list_reviews(self) -> tuple[PostTradeReviewRecord, ...]: ...
    def has_review(self, trade_id: UUID) -> bool: ...


def _review_values(record: PostTradeReviewRecord) -> dict[str, Any]:
    metrics = record.metrics
    return {
        "review_id": record.review_id,
        "trade_id": record.trade_id,
        "position_id": record.position_id,
        "instrument_id": record.instrument_id,
        "strategy_id": record.strategy_id,
        "strategy_version": record.strategy_version,
        "direction": record.direction.value,
        "opened_at": record.opened_at,
        "closed_at": record.closed_at,
        "exit_reason": record.exit_reason,
        "pnl_gross": metrics.pnl_gross,
        "pnl_net": metrics.pnl_net,
        "fees": metrics.fees,
        "slippage": metrics.slippage,
        "r_multiple": metrics.r_multiple,
        "alpha_pct": metrics.alpha_pct,
        "mae_pct": metrics.mae_pct,
        "mfe_pct": metrics.mfe_pct,
        "holding_seconds": metrics.holding_seconds,
        "entry_efficiency": metrics.entry_efficiency,
        "exit_efficiency": metrics.exit_efficiency,
        "prediction_error_pct": metrics.prediction_error_pct,
        "signal_calibration_error": metrics.signal_calibration_error,
        "expected_return_pct": metrics.expected_return_pct,
        "actual_return_pct": metrics.actual_return_pct,
        "benchmark_return_pct": metrics.benchmark_return_pct,
        "expected_r": metrics.expected_r,
        "market_regime": metrics.market_regime,
        "verdict": record.verdict,
        "postmortem_completed": record.postmortem_completed,
        "review_payload": record.review_payload,
        "artifact_key": record.artifact_key,
        "vault_path": record.vault_path,
        "episode_id": record.episode_id,
        "trace_id": record.trace_id,
        "created_at": record.created_at,
        "schema_version": record.schema_version,
    }


def _review_from_row(row: Any) -> PostTradeReviewRecord:
    return PostTradeReviewRecord.model_validate(
        {
            "review_id": row.review_id,
            "trade_id": row.trade_id,
            "position_id": row.position_id,
            "instrument_id": row.instrument_id,
            "strategy_id": row.strategy_id,
            "strategy_version": row.strategy_version,
            "direction": row.direction,
            "opened_at": row.opened_at,
            "closed_at": row.closed_at,
            "exit_reason": row.exit_reason,
            "metrics": {
                "pnl_gross": row.pnl_gross,
                "pnl_net": row.pnl_net,
                "fees": row.fees,
                "slippage": row.slippage,
                "r_multiple": row.r_multiple,
                "alpha_pct": row.alpha_pct,
                "mae_pct": row.mae_pct,
                "mfe_pct": row.mfe_pct,
                "holding_seconds": row.holding_seconds,
                "entry_efficiency": row.entry_efficiency,
                "exit_efficiency": row.exit_efficiency,
                "prediction_error_pct": row.prediction_error_pct,
                "signal_calibration_error": row.signal_calibration_error or {},
                "expected_return_pct": row.expected_return_pct,
                "actual_return_pct": row.actual_return_pct,
                "benchmark_return_pct": row.benchmark_return_pct,
                "expected_r": row.expected_r,
                "market_regime": row.market_regime,
            },
            "verdict": row.verdict,
            "postmortem_completed": row.postmortem_completed,
            "review_payload": row.review_payload,
            "artifact_key": row.artifact_key,
            "vault_path": row.vault_path,
            "episode_id": row.episode_id,
            "trace_id": row.trace_id,
            "created_at": row.created_at,
            "schema_version": row.schema_version,
        }
    )


class InMemoryPostTradeStore:
    """In-memory mirror of the PostgreSQL store (unit tests, dev)."""

    def __init__(self) -> None:
        self._reviews: dict[UUID, PostTradeReviewRecord] = {}
        self._by_trade: dict[UUID, UUID] = {}

    def save_review(self, record: PostTradeReviewRecord) -> PostTradeReviewRecord:
        existing = self._reviews.get(record.review_id)
        if existing is not None:
            return existing
        self._reviews[record.review_id] = record
        self._by_trade[record.trade_id] = record.review_id
        return record

    def get_review(self, review_id: UUID) -> PostTradeReviewRecord | None:
        return self._reviews.get(review_id)

    def get_by_trade(self, trade_id: UUID) -> PostTradeReviewRecord | None:
        review_id = self._by_trade.get(trade_id)
        return self._reviews.get(review_id) if review_id is not None else None

    def list_reviews(self) -> tuple[PostTradeReviewRecord, ...]:
        return tuple(self._reviews.values())

    def has_review(self, trade_id: UUID) -> bool:
        return trade_id in self._by_trade


def _retry[T](
    operation: Callable[[], T],
    *,
    name: str,
    base: float = 0.5,
    cap: float = 15.0,
    attempts: int = 8,
) -> T:
    """Retry transient database failures with exponential backoff."""
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except _RETRYABLE as exc:
            if attempt >= attempts:
                raise
            delay = min(base * (2 ** (attempt - 1)), cap)
            logger.warning(
                "postgres %s failed (attempt %d): %s; retrying in %.1fs", name, attempt, exc, delay
            )
            time.sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover


class PostgresPostTradeStore:
    """SQLAlchemy Core store for canonical postmortem metrics."""

    def __init__(self, dsn: str) -> None:
        self._engine: Engine = create_engine(ensure_psycopg_dsn(dsn), pool_pre_ping=True)

    def save_review(self, record: PostTradeReviewRecord) -> PostTradeReviewRecord:
        def _op() -> PostTradeReviewRecord:
            with self._engine.begin() as conn:
                existing = conn.execute(
                    select(posttrade_reviews_table).where(
                        posttrade_reviews_table.c.review_id == record.review_id
                    )
                ).first()
                if existing is not None:
                    return _review_from_row(existing)
                conn.execute(posttrade_reviews_table.insert().values(_review_values(record)))
                return record

        return _retry(_op, name="save_review")

    def get_review(self, review_id: UUID) -> PostTradeReviewRecord | None:
        def _op() -> PostTradeReviewRecord | None:
            with self._engine.connect() as conn:
                row = conn.execute(
                    select(posttrade_reviews_table).where(
                        posttrade_reviews_table.c.review_id == review_id
                    )
                ).first()
                return _review_from_row(row) if row is not None else None

        return _retry(_op, name="get_review")

    def get_by_trade(self, trade_id: UUID) -> PostTradeReviewRecord | None:
        def _op() -> PostTradeReviewRecord | None:
            with self._engine.connect() as conn:
                row = conn.execute(
                    select(posttrade_reviews_table).where(
                        posttrade_reviews_table.c.trade_id == trade_id
                    )
                ).first()
                return _review_from_row(row) if row is not None else None

        return _retry(_op, name="get_by_trade")

    def list_reviews(self) -> tuple[PostTradeReviewRecord, ...]:
        def _op() -> tuple[PostTradeReviewRecord, ...]:
            with self._engine.connect() as conn:
                rows = conn.execute(select(posttrade_reviews_table)).all()
                return tuple(_review_from_row(row) for row in rows)

        return _retry(_op, name="list_reviews")

    def has_review(self, trade_id: UUID) -> bool:
        return self.get_by_trade(trade_id) is not None
