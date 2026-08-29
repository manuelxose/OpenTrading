"""Pipeline persistence: run ledger, trade lifecycles, paper account.

Three SQLAlchemy Core tables (mirrored by Alembic migration ``0004``) back the
autonomous pipeline:

- ``pipeline_runs`` — the idempotency ledger: one row per ``(trace_id, stage)``;
- ``trade_lifecycles`` — high-level trade state, CAS-guarded by ``version``;
- ``paper_accounts`` — authoritative paper account, CAS-guarded by ``version``.

The PostgreSQL store retries transient ``OperationalError``s (database restart)
with exponential backoff and enables ``pool_pre_ping`` so a reconnected pool
never hands out dead connections — the pipeline keeps operating unattended
while PostgreSQL is briefly unavailable. Only idempotent writes (inserts,
upserts, compare-and-set updates) are retried.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from core.config.settings import ensure_psycopg_dsn
from core.domain.enums import PipelineStageName, PipelineStatus
from core.schemas.pipeline import PaperAccountRecord, PipelineRunRecord, TradeLifecycle
from core.schemas.posttrade import TradeContextRecord
from sqlalchemy import (
    Column,
    DateTime,
    Engine,
    Integer,
    MetaData,
    Numeric,
    Table,
    Text,
    Uuid,
    create_engine,
    select,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import OperationalError

__all__ = [
    "InMemoryPipelineStore",
    "PipelineStore",
    "PostgresPipelineStore",
    "StalePipelineStateError",
    "paper_accounts_table",
    "pipeline_runs_table",
    "trade_contexts_table",
    "trade_lifecycles_table",
]

logger = logging.getLogger(__name__)

_RETRYABLE = (OperationalError,)


class StalePipelineStateError(RuntimeError):
    """Raised when a CAS update loses a race against another writer."""

    def __init__(self, key: str, expected_version: int, actual_version: int) -> None:
        super().__init__(
            f"stale pipeline state for {key}: expected version {expected_version}, "
            f"found {actual_version}"
        )
        self.key = key
        self.expected_version = expected_version
        self.actual_version = actual_version


metadata = MetaData()

pipeline_runs_table = Table(
    "pipeline_runs",
    metadata,
    Column("run_id", Uuid, primary_key=True),
    Column("trace_id", Uuid, nullable=False),
    Column("cycle_id", Text, nullable=False),
    Column("instrument_id", Text, nullable=False),
    Column("stage", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("attempt", Integer, nullable=False, server_default=text("1")),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True), nullable=True),
    Column("error", Text, nullable=True),
    Column("input_refs", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("output_refs", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
)

trade_lifecycles_table = Table(
    "trade_lifecycles",
    metadata,
    Column("lifecycle_id", Uuid, primary_key=True),
    Column("trace_id", Uuid, nullable=False),
    Column("proposal_id", Uuid, nullable=True),
    Column("strategy_id", Text, nullable=False),
    Column("strategy_version", Text, nullable=False),
    Column("instrument_id", Text, nullable=False),
    Column("state", Text, nullable=False),
    Column("version", Integer, nullable=False),
    Column("direction", Text, nullable=True),
    Column("risk_decision_id", Uuid, nullable=True),
    Column("order_intent_id", Uuid, nullable=True),
    Column("position_id", Text, nullable=True),
    Column("trade_id", Uuid, nullable=True),
    Column("stop_loss", Numeric(38, 8), nullable=True),
    Column("take_profit", Numeric(38, 8), nullable=True),
    Column("error", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

paper_accounts_table = Table(
    "paper_accounts",
    metadata,
    Column("account_id", Text, primary_key=True),
    Column("currency", Text, nullable=False),
    Column("balance", Numeric(38, 8), nullable=False),
    Column("equity", Numeric(38, 8), nullable=False),
    Column("realized_pnl", Numeric(38, 8), nullable=False),
    Column("daily_pnl", Numeric(38, 8), nullable=False),
    Column("peak_equity", Numeric(38, 8), nullable=False),
    Column("consecutive_losses", Integer, nullable=False),
    Column("last_loss_at", DateTime(timezone=True), nullable=True),
    Column("open_positions", Integer, nullable=False),
    Column("version", Integer, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

trade_contexts_table = Table(
    "trade_contexts",
    metadata,
    Column("trace_id", Uuid, primary_key=True),
    Column("instrument_id", Text, nullable=False),
    Column("fragments", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


class PipelineStore(Protocol):
    """Authoritative pipeline-state persistence boundary (INV-6, Phase 7)."""

    # ── pipeline runs ─────────────────────────────────────────────────────────

    def save_run(self, record: PipelineRunRecord) -> PipelineRunRecord:
        """Insert one run record. Idempotent per (trace_id, stage): a second
        insert for an existing pair returns the stored record unchanged."""
        ...

    def get_run(self, trace_id: UUID, stage: PipelineStageName) -> PipelineRunRecord | None: ...
    def runs_for_trace(self, trace_id: UUID) -> tuple[PipelineRunRecord, ...]: ...
    def has_succeeded(self, trace_id: UUID, stage: PipelineStageName) -> bool: ...
    def list_runs(self) -> tuple[PipelineRunRecord, ...]: ...

    # ── trade lifecycles ──────────────────────────────────────────────────────

    def save_lifecycle(self, lifecycle: TradeLifecycle) -> TradeLifecycle: ...
    def get_lifecycle(self, lifecycle_id: UUID) -> TradeLifecycle | None: ...
    def get_lifecycle_by_proposal(self, proposal_id: UUID) -> TradeLifecycle | None: ...
    def get_lifecycle_by_order(self, order_intent_id: UUID) -> TradeLifecycle | None: ...
    def get_lifecycle_by_trace(self, trace_id: UUID) -> TradeLifecycle | None: ...
    def update_lifecycle(
        self, lifecycle: TradeLifecycle, expected_version: int
    ) -> TradeLifecycle: ...
    def list_lifecycles(self) -> tuple[TradeLifecycle, ...]: ...

    # ── paper account ─────────────────────────────────────────────────────────

    def get_account(self, account_id: str) -> PaperAccountRecord | None: ...
    def upsert_account(
        self, record: PaperAccountRecord, expected_version: int | None
    ) -> PaperAccountRecord: ...

    # ── trade context (post-trade learning loop) ────────────────────────────

    def save_context_fragment(
        self,
        trace_id: UUID,
        key: str,
        payload: dict[str, Any],
        *,
        instrument_id: str,
        updated_at: datetime,
    ) -> None: ...
    def get_context(self, trace_id: UUID) -> TradeContextRecord | None: ...


def _run_values(record: PipelineRunRecord) -> dict[str, Any]:
    return {
        "run_id": record.run_id,
        "trace_id": record.trace_id,
        "cycle_id": record.cycle_id,
        "instrument_id": record.instrument_id,
        "stage": record.stage.value,
        "status": record.status.value,
        "attempt": record.attempt,
        "started_at": record.started_at,
        "completed_at": record.completed_at,
        "error": record.error,
        "input_refs": record.input_refs,
        "output_refs": record.output_refs,
    }


def _run_from_row(row: Any) -> PipelineRunRecord:
    return PipelineRunRecord.model_validate(
        {
            "run_id": row.run_id,
            "trace_id": row.trace_id,
            "cycle_id": row.cycle_id,
            "instrument_id": row.instrument_id,
            "stage": row.stage,
            "status": row.status,
            "attempt": row.attempt,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "error": row.error,
            "input_refs": row.input_refs,
            "output_refs": row.output_refs,
        }
    )


def _lifecycle_values(lifecycle: TradeLifecycle) -> dict[str, Any]:
    return {
        "lifecycle_id": lifecycle.lifecycle_id,
        "trace_id": lifecycle.trace_id,
        "proposal_id": lifecycle.proposal_id,
        "strategy_id": lifecycle.strategy_id,
        "strategy_version": lifecycle.strategy_version,
        "instrument_id": lifecycle.instrument_id,
        "state": lifecycle.state.value,
        "version": lifecycle.version,
        "direction": lifecycle.direction.value if lifecycle.direction is not None else None,
        "risk_decision_id": lifecycle.risk_decision_id,
        "order_intent_id": lifecycle.order_intent_id,
        "position_id": lifecycle.position_id,
        "trade_id": lifecycle.trade_id,
        "stop_loss": lifecycle.stop_loss,
        "take_profit": lifecycle.take_profit,
        "error": lifecycle.error,
        "created_at": lifecycle.created_at,
        "updated_at": lifecycle.updated_at,
    }


def _lifecycle_from_row(row: Any) -> TradeLifecycle:
    return TradeLifecycle.model_validate(
        {
            "lifecycle_id": row.lifecycle_id,
            "trace_id": row.trace_id,
            "proposal_id": row.proposal_id,
            "strategy_id": row.strategy_id,
            "strategy_version": row.strategy_version,
            "instrument_id": row.instrument_id,
            "state": row.state,
            "version": row.version,
            "direction": row.direction,
            "risk_decision_id": row.risk_decision_id,
            "order_intent_id": row.order_intent_id,
            "position_id": row.position_id,
            "trade_id": row.trade_id,
            "stop_loss": row.stop_loss,
            "take_profit": row.take_profit,
            "error": row.error,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )


def _account_values(record: PaperAccountRecord) -> dict[str, Any]:
    return {
        "account_id": record.account_id,
        "currency": record.currency,
        "balance": record.balance,
        "equity": record.equity,
        "realized_pnl": record.realized_pnl,
        "daily_pnl": record.daily_pnl,
        "peak_equity": record.peak_equity,
        "consecutive_losses": record.consecutive_losses,
        "last_loss_at": record.last_loss_at,
        "open_positions": record.open_positions,
        "version": record.version,
        "updated_at": record.updated_at,
    }


def _account_from_row(row: Any) -> PaperAccountRecord:
    return PaperAccountRecord.model_validate(
        {
            "account_id": row.account_id,
            "currency": row.currency,
            "balance": row.balance,
            "equity": row.equity,
            "realized_pnl": row.realized_pnl,
            "daily_pnl": row.daily_pnl,
            "peak_equity": row.peak_equity,
            "consecutive_losses": row.consecutive_losses,
            "last_loss_at": row.last_loss_at,
            "open_positions": row.open_positions,
            "version": row.version,
            "updated_at": row.updated_at,
        }
    )


def _context_from_row(row: Any) -> TradeContextRecord:
    return TradeContextRecord.model_validate(
        {
            "trace_id": row.trace_id,
            "instrument_id": row.instrument_id,
            "fragments": row.fragments,
            "updated_at": row.updated_at,
        }
    )


class InMemoryPipelineStore:
    """In-memory mirror of the PostgreSQL store (unit tests, dev)."""

    def __init__(self) -> None:
        self._runs: dict[tuple[UUID, PipelineStageName], PipelineRunRecord] = {}
        self._lifecycles: dict[UUID, TradeLifecycle] = {}
        self._by_proposal: dict[UUID, UUID] = {}
        self._by_order: dict[UUID, UUID] = {}
        self._by_trace: dict[UUID, UUID] = {}
        self._accounts: dict[str, PaperAccountRecord] = {}
        self._contexts: dict[UUID, TradeContextRecord] = {}

    # ── pipeline runs ─────────────────────────────────────────────────────────

    def save_run(self, record: PipelineRunRecord) -> PipelineRunRecord:
        key = (record.trace_id, record.stage)
        existing = self._runs.get(key)
        if existing is not None and existing.status in (
            PipelineStatus.SUCCEEDED,
            PipelineStatus.SKIPPED,
        ):
            return existing  # idempotent; terminal results are immutable
        self._runs[key] = record  # first attempt or retry of a failed run
        return record

    def get_run(self, trace_id: UUID, stage: PipelineStageName) -> PipelineRunRecord | None:
        return self._runs.get((trace_id, stage))

    def runs_for_trace(self, trace_id: UUID) -> tuple[PipelineRunRecord, ...]:
        return tuple(r for (tid, _stage), r in self._runs.items() if tid == trace_id)

    def has_succeeded(self, trace_id: UUID, stage: PipelineStageName) -> bool:
        record = self._runs.get((trace_id, stage))
        return record is not None and record.status is PipelineStatus.SUCCEEDED

    def list_runs(self) -> tuple[PipelineRunRecord, ...]:
        return tuple(self._runs.values())

    # ── trade lifecycles ──────────────────────────────────────────────────────

    def save_lifecycle(self, lifecycle: TradeLifecycle) -> TradeLifecycle:
        if lifecycle.lifecycle_id in self._lifecycles:
            return self._lifecycles[lifecycle.lifecycle_id]  # idempotent
        self._lifecycles[lifecycle.lifecycle_id] = lifecycle
        if lifecycle.proposal_id is not None:
            self._by_proposal[lifecycle.proposal_id] = lifecycle.lifecycle_id
        if lifecycle.order_intent_id is not None:
            self._by_order[lifecycle.order_intent_id] = lifecycle.lifecycle_id
        self._by_trace.setdefault(lifecycle.trace_id, lifecycle.lifecycle_id)
        return lifecycle

    def get_lifecycle(self, lifecycle_id: UUID) -> TradeLifecycle | None:
        return self._lifecycles.get(lifecycle_id)

    def get_lifecycle_by_proposal(self, proposal_id: UUID) -> TradeLifecycle | None:
        lifecycle_id = self._by_proposal.get(proposal_id)
        return self._lifecycles.get(lifecycle_id) if lifecycle_id else None

    def get_lifecycle_by_order(self, order_intent_id: UUID) -> TradeLifecycle | None:
        lifecycle_id = self._by_order.get(order_intent_id)
        return self._lifecycles.get(lifecycle_id) if lifecycle_id else None

    def get_lifecycle_by_trace(self, trace_id: UUID) -> TradeLifecycle | None:
        lifecycle_id = self._by_trace.get(trace_id)
        return self._lifecycles.get(lifecycle_id) if lifecycle_id else None

    def update_lifecycle(self, lifecycle: TradeLifecycle, expected_version: int) -> TradeLifecycle:
        current = self._lifecycles.get(lifecycle.lifecycle_id)
        if current is None:
            raise StalePipelineStateError(str(lifecycle.lifecycle_id), expected_version, 0)
        if current.version != expected_version:
            raise StalePipelineStateError(
                str(lifecycle.lifecycle_id), expected_version, current.version
            )
        if lifecycle.version != expected_version + 1:
            raise ValueError(
                f"update_lifecycle requires version {expected_version + 1}, got {lifecycle.version}"
            )
        self._lifecycles[lifecycle.lifecycle_id] = lifecycle
        return lifecycle

    def list_lifecycles(self) -> tuple[TradeLifecycle, ...]:
        return tuple(self._lifecycles.values())

    # ── paper account ─────────────────────────────────────────────────────────

    def get_account(self, account_id: str) -> PaperAccountRecord | None:
        return self._accounts.get(account_id)

    def upsert_account(
        self, record: PaperAccountRecord, expected_version: int | None
    ) -> PaperAccountRecord:
        current = self._accounts.get(record.account_id)
        if expected_version is not None and record.version != expected_version + 1:
            raise ValueError(
                f"upsert_account requires version {expected_version + 1}, got {record.version}"
            )
        if current is None:
            self._accounts[record.account_id] = record
            return record
        if expected_version is not None and current.version != expected_version:
            raise StalePipelineStateError(record.account_id, expected_version, current.version)
        self._accounts[record.account_id] = record
        return record

    # ── trade context ────────────────────────────────────────────────────────

    def save_context_fragment(
        self,
        trace_id: UUID,
        key: str,
        payload: dict[str, Any],
        *,
        instrument_id: str,
        updated_at: datetime,
    ) -> None:
        existing = self._contexts.get(trace_id)
        if existing is None:
            self._contexts[trace_id] = TradeContextRecord(
                trace_id=trace_id,
                instrument_id=instrument_id,
                fragments={key: payload},
                updated_at=updated_at,
            )
            return
        fragments = dict(existing.fragments)
        fragments[key] = payload
        self._contexts[trace_id] = existing.model_copy(
            update={"fragments": fragments, "updated_at": updated_at}
        )

    def get_context(self, trace_id: UUID) -> TradeContextRecord | None:
        return self._contexts.get(trace_id)


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


class PostgresPipelineStore:
    """SQLAlchemy Core store against PostgreSQL (transactional source of truth)."""

    def __init__(self, dsn: str) -> None:
        self._engine: Engine = create_engine(ensure_psycopg_dsn(dsn), pool_pre_ping=True)

    # ── pipeline runs ─────────────────────────────────────────────────────────

    def save_run(self, record: PipelineRunRecord) -> PipelineRunRecord:
        def _op() -> PipelineRunRecord:
            with self._engine.begin() as conn:
                existing = conn.execute(
                    select(pipeline_runs_table).where(
                        pipeline_runs_table.c.trace_id == record.trace_id,
                        pipeline_runs_table.c.stage == record.stage.value,
                    )
                ).first()
                if existing is not None and existing.status in (
                    PipelineStatus.SUCCEEDED.value,
                    PipelineStatus.SKIPPED.value,
                ):
                    return _run_from_row(existing)
                if existing is not None:
                    # Retry of a failed/interrupted run: replace the row.
                    conn.execute(
                        pipeline_runs_table.update()
                        .where(
                            pipeline_runs_table.c.trace_id == record.trace_id,
                            pipeline_runs_table.c.stage == record.stage.value,
                        )
                        .values(_run_values(record))
                    )
                    return record
                conn.execute(pipeline_runs_table.insert().values(_run_values(record)))
                return record

        return _retry(_op, name="save_run")

    def get_run(self, trace_id: UUID, stage: PipelineStageName) -> PipelineRunRecord | None:
        def _op() -> PipelineRunRecord | None:
            with self._engine.connect() as conn:
                row = conn.execute(
                    select(pipeline_runs_table).where(
                        pipeline_runs_table.c.trace_id == trace_id,
                        pipeline_runs_table.c.stage == stage.value,
                    )
                ).first()
            return _run_from_row(row) if row is not None else None

        return _retry(_op, name="get_run")

    def runs_for_trace(self, trace_id: UUID) -> tuple[PipelineRunRecord, ...]:
        def _op() -> tuple[PipelineRunRecord, ...]:
            with self._engine.connect() as conn:
                rows = conn.execute(
                    select(pipeline_runs_table)
                    .where(pipeline_runs_table.c.trace_id == trace_id)
                    .order_by("started_at")
                ).all()
            return tuple(_run_from_row(row) for row in rows)

        return _retry(_op, name="runs_for_trace")

    def has_succeeded(self, trace_id: UUID, stage: PipelineStageName) -> bool:
        record = self.get_run(trace_id, stage)
        return record is not None and record.status is PipelineStatus.SUCCEEDED

    def list_runs(self) -> tuple[PipelineRunRecord, ...]:
        def _op() -> tuple[PipelineRunRecord, ...]:
            with self._engine.connect() as conn:
                rows = conn.execute(select(pipeline_runs_table).order_by("started_at")).all()
            return tuple(_run_from_row(row) for row in rows)

        return _retry(_op, name="list_runs")

    # ── trade lifecycles ──────────────────────────────────────────────────────

    def save_lifecycle(self, lifecycle: TradeLifecycle) -> TradeLifecycle:
        def _op() -> TradeLifecycle:
            with self._engine.begin() as conn:
                existing = conn.execute(
                    select(trade_lifecycles_table).where(
                        trade_lifecycles_table.c.lifecycle_id == lifecycle.lifecycle_id
                    )
                ).first()
                if existing is not None:
                    return _lifecycle_from_row(existing)
                conn.execute(trade_lifecycles_table.insert().values(_lifecycle_values(lifecycle)))
                return lifecycle

        return _retry(_op, name="save_lifecycle")

    def get_lifecycle(self, lifecycle_id: UUID) -> TradeLifecycle | None:
        return self._get_lifecycle_where(trade_lifecycles_table.c.lifecycle_id == lifecycle_id)

    def get_lifecycle_by_proposal(self, proposal_id: UUID) -> TradeLifecycle | None:
        return self._get_lifecycle_where(trade_lifecycles_table.c.proposal_id == proposal_id)

    def get_lifecycle_by_order(self, order_intent_id: UUID) -> TradeLifecycle | None:
        return self._get_lifecycle_where(
            trade_lifecycles_table.c.order_intent_id == order_intent_id
        )

    def get_lifecycle_by_trace(self, trace_id: UUID) -> TradeLifecycle | None:
        return self._get_lifecycle_where(trade_lifecycles_table.c.trace_id == trace_id)

    def _get_lifecycle_where(self, condition: Any) -> TradeLifecycle | None:
        def _op() -> TradeLifecycle | None:
            with self._engine.connect() as conn:
                row = conn.execute(select(trade_lifecycles_table).where(condition)).first()
            return _lifecycle_from_row(row) if row is not None else None

        return _retry(_op, name="get_lifecycle")

    def update_lifecycle(self, lifecycle: TradeLifecycle, expected_version: int) -> TradeLifecycle:
        def _op() -> TradeLifecycle:
            with self._engine.begin() as conn:
                result = conn.execute(
                    trade_lifecycles_table.update()
                    .where(
                        trade_lifecycles_table.c.lifecycle_id == lifecycle.lifecycle_id,
                        trade_lifecycles_table.c.version == expected_version,
                    )
                    .values(_lifecycle_values(lifecycle))
                )
                if result.rowcount != 1:
                    current = conn.execute(
                        select(trade_lifecycles_table.c.version).where(
                            trade_lifecycles_table.c.lifecycle_id == lifecycle.lifecycle_id
                        )
                    ).scalar()
                    raise StalePipelineStateError(
                        str(lifecycle.lifecycle_id),
                        expected_version,
                        int(current) if current is not None else 0,
                    )
                return lifecycle

        return _retry(_op, name="update_lifecycle")

    def list_lifecycles(self) -> tuple[TradeLifecycle, ...]:
        def _op() -> tuple[TradeLifecycle, ...]:
            with self._engine.connect() as conn:
                rows = conn.execute(select(trade_lifecycles_table).order_by("created_at")).all()
            return tuple(_lifecycle_from_row(row) for row in rows)

        return _retry(_op, name="list_lifecycles")

    # ── paper account ─────────────────────────────────────────────────────────

    def get_account(self, account_id: str) -> PaperAccountRecord | None:
        def _op() -> PaperAccountRecord | None:
            with self._engine.connect() as conn:
                row = conn.execute(
                    select(paper_accounts_table).where(
                        paper_accounts_table.c.account_id == account_id
                    )
                ).first()
            return _account_from_row(row) if row is not None else None

        return _retry(_op, name="get_account")

    def upsert_account(
        self, record: PaperAccountRecord, expected_version: int | None
    ) -> PaperAccountRecord:
        if expected_version is not None and record.version != expected_version + 1:
            raise ValueError(
                f"upsert_account requires version {expected_version + 1}, got {record.version}"
            )

        def _op() -> PaperAccountRecord:
            values = _account_values(record)
            with self._engine.begin() as conn:
                if expected_version is None:
                    conn.execute(
                        postgresql.insert(paper_accounts_table)
                        .values(**values)
                        .on_conflict_do_update(
                            index_elements=["account_id"],
                            set_={k: values[k] for k in values if k != "account_id"},
                        )
                    )
                    return record
                result = conn.execute(
                    paper_accounts_table.update()
                    .where(
                        paper_accounts_table.c.account_id == record.account_id,
                        paper_accounts_table.c.version == expected_version,
                    )
                    .values(**values)
                )
                if result.rowcount != 1:
                    current = conn.execute(
                        select(paper_accounts_table.c.version).where(
                            paper_accounts_table.c.account_id == record.account_id
                        )
                    ).scalar()
                    raise StalePipelineStateError(
                        record.account_id,
                        expected_version,
                        int(current) if current is not None else 0,
                    )
                return record

        return _retry(_op, name="upsert_account")

    # ── trade context ────────────────────────────────────────────────────────

    def save_context_fragment(
        self,
        trace_id: UUID,
        key: str,
        payload: dict[str, Any],
        *,
        instrument_id: str,
        updated_at: datetime,
    ) -> None:
        def _op() -> None:
            with self._engine.begin() as conn:
                row = conn.execute(
                    select(trade_contexts_table).where(trade_contexts_table.c.trace_id == trace_id)
                ).first()
                if row is None:
                    conn.execute(
                        trade_contexts_table.insert().values(
                            trace_id=trace_id,
                            instrument_id=instrument_id,
                            fragments={key: payload},
                            updated_at=updated_at,
                        )
                    )
                    return
                fragments = dict(row.fragments or {})
                fragments[key] = payload
                conn.execute(
                    trade_contexts_table.update()
                    .where(trade_contexts_table.c.trace_id == trace_id)
                    .values(fragments=fragments, updated_at=updated_at)
                )

        _retry(_op, name="save_context_fragment")

    def get_context(self, trace_id: UUID) -> TradeContextRecord | None:
        def _op() -> TradeContextRecord | None:
            with self._engine.connect() as conn:
                row = conn.execute(
                    select(trade_contexts_table).where(trade_contexts_table.c.trace_id == trace_id)
                ).first()
                return _context_from_row(row) if row is not None else None

        return _retry(_op, name="get_context")
