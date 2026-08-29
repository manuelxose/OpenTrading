"""PostgreSQL persistence for authoritative execution state (INV-6, §9).

Four SQLAlchemy Core tables mirror the pydantic contracts in
:mod:`core.schemas.execution`:

- ``execution_orders``     — one row per ``order_intent_id`` (the canonical
  idempotency key, INV-2), carrying the full lifecycle state. ``version`` is
  guarded by compare-and-set so concurrent writers cannot silently overwrite
  state.
- ``execution_positions``  — broker-side positions observed through fills and
  reconciliation.
- ``reconciliation_runs``  — every mandatory reconciliation pass, with its
  discrepancies (JSONB) and outcome counters.
- ``safe_mode_state``      — the SAFE_MODE singleton row.

Alembic migration ``0003_execution_state`` mirrors these definitions
(self-contained DDL, per repo convention); keep both in sync on change.

Unit tests inject :class:`InMemoryExecutionStateStore` (no PostgreSQL in CI);
:class:`PostgresExecutionStateStore` is exercised by the docker-gated
integration suite.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from core.config.settings import ensure_psycopg_dsn
from core.schemas.execution import (
    ExecutionPosition,
    OrderRecord,
    ReconciliationRun,
    SafeModeRecord,
)
from sqlalchemy import (
    Boolean,
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

__all__ = [
    "SAFE_MODE_SINGLETON_ID",
    "ExecutionStateStore",
    "InMemoryExecutionStateStore",
    "PostgresExecutionStateStore",
    "StaleStateError",
    "execution_orders_table",
    "execution_positions_table",
    "reconciliation_runs_table",
    "safe_mode_state_table",
]

SAFE_MODE_SINGLETON_ID = 1


class StaleStateError(RuntimeError):
    """Raised when an order update races another writer (optimistic concurrency)."""

    def __init__(self, order_intent_id: UUID, expected_version: int, actual_version: int) -> None:
        super().__init__(
            f"stale order state for {order_intent_id}: expected version "
            f"{expected_version}, found {actual_version}"
        )
        self.order_intent_id = order_intent_id
        self.expected_version = expected_version
        self.actual_version = actual_version


metadata = MetaData()

execution_orders_table = Table(
    "execution_orders",
    metadata,
    Column("order_intent_id", Uuid, primary_key=True),
    Column("state", Text, nullable=False),
    Column("strategy_id", Text, nullable=False),
    Column("strategy_version", Text, nullable=False),
    Column("instrument_id", Text, nullable=False),
    Column("venue", Text, nullable=True),
    Column("side", Text, nullable=False),
    Column("order_type", Text, nullable=False),
    Column("requested_quantity", Numeric(38, 8), nullable=False),
    Column("filled_quantity", Numeric(38, 8), nullable=False),
    Column("remaining_quantity", Numeric(38, 8), nullable=False),
    Column("average_fill_price", Numeric(38, 8), nullable=True),
    Column("venue_order_id", Text, nullable=True),
    Column("venue_position_id", Text, nullable=True),
    Column("commission", Numeric(38, 8), nullable=False, server_default=text("0")),
    Column("fees", Numeric(38, 8), nullable=False, server_default=text("0")),
    Column("slippage", Numeric(38, 8), nullable=True),
    Column("reject_reason", Text, nullable=True),
    Column("last_event_sequence", Integer, nullable=False, server_default=text("0")),
    Column("processed_event_ids", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("submitted_at", DateTime(timezone=True), nullable=True),
    Column("acknowledged_at", DateTime(timezone=True), nullable=True),
    Column("filled_at", DateTime(timezone=True), nullable=True),
    Column("cancelled_at", DateTime(timezone=True), nullable=True),
    Column("rejected_at", DateTime(timezone=True), nullable=True),
    Column("reconciled_at", DateTime(timezone=True), nullable=True),
    Column("closed_at", DateTime(timezone=True), nullable=True),
    Column("reviewed_at", DateTime(timezone=True), nullable=True),
    Column("reconciliation_note", Text, nullable=True),
)

execution_positions_table = Table(
    "execution_positions",
    metadata,
    Column("venue_position_id", Text, primary_key=True),
    Column("account_id", Text, nullable=False),
    Column("instrument_id", Text, nullable=False),
    Column("side", Text, nullable=False),
    Column("quantity", Numeric(38, 8), nullable=False),
    Column("average_entry_price", Numeric(38, 8), nullable=False),
    Column("order_intent_id", Uuid, nullable=True),
    Column("opened_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("closed_at", DateTime(timezone=True), nullable=True),
)

reconciliation_runs_table = Table(
    "reconciliation_runs",
    metadata,
    Column("run_id", Uuid, primary_key=True),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("compared_at", DateTime(timezone=True), nullable=False),
    Column("broker_reachable", Boolean, nullable=False),
    Column("broker_connected", Boolean, nullable=False, server_default=text("true")),
    Column("trading_enabled", Boolean, nullable=False, server_default=text("true")),
    Column("account", JSONB, nullable=True),
    Column("discrepancies", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("material_discrepancies", Integer, nullable=False, server_default=text("0")),
    Column("orders_reconciled", Integer, nullable=False, server_default=text("0")),
    Column("orders_resolved", Integer, nullable=False, server_default=text("0")),
    Column("positions_adopted", Integer, nullable=False, server_default=text("0")),
    Column("positions_closed", Integer, nullable=False, server_default=text("0")),
    Column("safe_mode_entered", Boolean, nullable=False, server_default=text("false")),
    Column("safe_mode_exited", Boolean, nullable=False, server_default=text("false")),
    Column("last_sequences", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
)

safe_mode_state_table = Table(
    "safe_mode_state",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("active", Boolean, nullable=False, server_default=text("false")),
    Column("since", DateTime(timezone=True), nullable=True),
    Column("reason_codes", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("note", Text, nullable=True),
    Column("exited_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


class ExecutionStateStore(Protocol):
    """Authoritative execution-state persistence boundary (INV-6)."""

    def save_order(self, record: OrderRecord) -> OrderRecord:
        """Insert a brand-new order record (version 1)."""
        ...

    def update_order(self, record: OrderRecord, expected_version: int) -> OrderRecord:
        """Compare-and-set update; raises :class:`StaleStateError` on conflict."""
        ...

    def get_order(self, order_intent_id: UUID) -> OrderRecord | None: ...

    def list_orders(self) -> tuple[OrderRecord, ...]:
        """All orders, oldest first (creation order)."""
        ...

    def upsert_position(self, position: ExecutionPosition) -> ExecutionPosition: ...

    def get_position(self, venue_position_id: str) -> ExecutionPosition | None: ...

    def list_positions(self, *, open_only: bool = True) -> tuple[ExecutionPosition, ...]: ...

    def save_reconciliation_run(self, run: ReconciliationRun) -> ReconciliationRun: ...

    def list_reconciliation_runs(self, *, limit: int = 20) -> tuple[ReconciliationRun, ...]: ...

    def get_safe_mode(self) -> SafeModeRecord:
        """Current SAFE_MODE state (inactive default when absent)."""
        ...

    def set_safe_mode(self, record: SafeModeRecord) -> SafeModeRecord: ...


def _empty_safe_mode(now: datetime) -> SafeModeRecord:
    return SafeModeRecord(active=False, updated_at=now)


#: Earliest representable timestamp, used as the "absent" placeholder.
_EPOCH = datetime.min.replace(tzinfo=UTC)


class InMemoryExecutionStateStore:
    """Deterministic in-memory store with the exact same semantics as Postgres."""

    def __init__(self) -> None:
        self._orders: dict[UUID, OrderRecord] = {}
        self._positions: dict[str, ExecutionPosition] = {}
        self._runs: list[ReconciliationRun] = []
        self._safe_mode: SafeModeRecord | None = None
        self._created_order: dict[UUID, datetime] = {}

    # ── Orders ────────────────────────────────────────────────────────────
    def save_order(self, record: OrderRecord) -> OrderRecord:
        if record.order_intent_id in self._orders:
            raise StaleStateError(
                record.order_intent_id, 0, self._orders[record.order_intent_id].version
            )
        if record.version != 1:
            raise ValueError("save_order requires a version-1 record")
        self._orders[record.order_intent_id] = record
        self._created_order[record.order_intent_id] = record.created_at
        return record

    def update_order(self, record: OrderRecord, expected_version: int) -> OrderRecord:
        current = self._orders.get(record.order_intent_id)
        if current is None:
            raise StaleStateError(record.order_intent_id, expected_version, 0)
        if current.version != expected_version:
            raise StaleStateError(record.order_intent_id, expected_version, current.version)
        if record.version != expected_version + 1:
            raise ValueError(
                f"update_order requires version {expected_version + 1}, got {record.version}"
            )
        self._orders[record.order_intent_id] = record
        return record

    def get_order(self, order_intent_id: UUID) -> OrderRecord | None:
        return self._orders.get(order_intent_id)

    def list_orders(self) -> tuple[OrderRecord, ...]:
        return tuple(
            sorted(
                self._orders.values(),
                key=lambda r: (self._created_order[r.order_intent_id], r.updated_at),
            )
        )

    # ── Positions ─────────────────────────────────────────────────────────
    def upsert_position(self, position: ExecutionPosition) -> ExecutionPosition:
        self._positions[position.venue_position_id] = position
        return position

    def get_position(self, venue_position_id: str) -> ExecutionPosition | None:
        return self._positions.get(venue_position_id)

    def list_positions(self, *, open_only: bool = True) -> tuple[ExecutionPosition, ...]:
        values = list(self._positions.values())
        if open_only:
            values = [p for p in values if p.closed_at is None]
        return tuple(sorted(values, key=lambda p: p.opened_at))

    # ── Reconciliation runs ───────────────────────────────────────────────
    def save_reconciliation_run(self, run: ReconciliationRun) -> ReconciliationRun:
        self._runs.append(run)
        return run

    def list_reconciliation_runs(self, *, limit: int = 20) -> tuple[ReconciliationRun, ...]:
        return tuple(self._runs[-limit:])

    # ── Safe mode ─────────────────────────────────────────────────────────
    def get_safe_mode(self) -> SafeModeRecord:
        return self._safe_mode if self._safe_mode is not None else _empty_safe_mode(_EPOCH)

    def set_safe_mode(self, record: SafeModeRecord) -> SafeModeRecord:
        self._safe_mode = record
        return record


#: Column list order shared by row <-> record mapping (must match table def).
_ORDER_COLUMNS = tuple(execution_orders_table.c)
_POSITION_COLUMNS = tuple(execution_positions_table.c)
_RUN_COLUMNS = tuple(reconciliation_runs_table.c)


def _row_to_order(row: object) -> OrderRecord:
    values = {column.key: getattr(row, column.key) for column in _ORDER_COLUMNS}
    return OrderRecord.model_validate(values)


def _order_values(record: OrderRecord) -> dict[str, object]:
    return record.model_dump(mode="json")


def _row_to_position(row: object) -> ExecutionPosition:
    values = {column.key: getattr(row, column.key) for column in _POSITION_COLUMNS}
    return ExecutionPosition.model_validate(values)


def _position_values(position: ExecutionPosition) -> dict[str, object]:
    return position.model_dump(mode="json")


def _row_to_run(row: object) -> ReconciliationRun:
    values = {column.key: getattr(row, column.key) for column in _RUN_COLUMNS}
    return ReconciliationRun.model_validate(values)


def _run_values(run: ReconciliationRun) -> dict[str, object]:
    return run.model_dump(mode="json")


class PostgresExecutionStateStore:
    """SQLAlchemy Core store against PostgreSQL (transactional source of truth)."""

    def __init__(self, dsn: str) -> None:
        self._engine: Engine = create_engine(ensure_psycopg_dsn(dsn))

    # ── Orders ────────────────────────────────────────────────────────────
    def save_order(self, record: OrderRecord) -> OrderRecord:
        if record.version != 1:
            raise ValueError("save_order requires a version-1 record")
        with self._engine.begin() as conn:
            conn.execute(execution_orders_table.insert().values(_order_values(record)))
        return record

    def update_order(self, record: OrderRecord, expected_version: int) -> OrderRecord:
        if record.version != expected_version + 1:
            raise ValueError(
                f"update_order requires version {expected_version + 1}, got {record.version}"
            )
        with self._engine.begin() as conn:
            result = conn.execute(
                execution_orders_table.update()
                .where(
                    execution_orders_table.c.order_intent_id == record.order_intent_id,
                    execution_orders_table.c.version == expected_version,
                )
                .values(_order_values(record))
            )
            if result.rowcount != 1:
                current = conn.execute(
                    select(execution_orders_table.c.version).where(
                        execution_orders_table.c.order_intent_id == record.order_intent_id
                    )
                ).scalar()
                raise StaleStateError(
                    record.order_intent_id,
                    expected_version,
                    int(current) if current is not None else 0,
                )
        return record

    def get_order(self, order_intent_id: UUID) -> OrderRecord | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(execution_orders_table).where(
                    execution_orders_table.c.order_intent_id == order_intent_id
                )
            ).first()
        return _row_to_order(row) if row is not None else None

    def list_orders(self) -> tuple[OrderRecord, ...]:
        with self._engine.connect() as conn:
            rows = conn.execute(select(execution_orders_table).order_by("created_at")).all()
        return tuple(_row_to_order(row) for row in rows)

    # ── Positions ─────────────────────────────────────────────────────────
    def upsert_position(self, position: ExecutionPosition) -> ExecutionPosition:
        values = _position_values(position)
        with self._engine.begin() as conn:
            conn.execute(
                postgresql.insert(execution_positions_table)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=["venue_position_id"],
                    set_={key: values[key] for key in values if key != "venue_position_id"},
                )
            )
        return position

    def get_position(self, venue_position_id: str) -> ExecutionPosition | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(execution_positions_table).where(
                    execution_positions_table.c.venue_position_id == venue_position_id
                )
            ).first()
        return _row_to_position(row) if row is not None else None

    def list_positions(self, *, open_only: bool = True) -> tuple[ExecutionPosition, ...]:
        query = select(execution_positions_table).order_by("opened_at")
        if open_only:
            query = query.where(execution_positions_table.c.closed_at.is_(None))
        with self._engine.connect() as conn:
            rows = conn.execute(query).all()
        return tuple(_row_to_position(row) for row in rows)

    # ── Reconciliation runs ───────────────────────────────────────────────
    def save_reconciliation_run(self, run: ReconciliationRun) -> ReconciliationRun:
        with self._engine.begin() as conn:
            conn.execute(reconciliation_runs_table.insert().values(_run_values(run)))
        return run

    def list_reconciliation_runs(self, *, limit: int = 20) -> tuple[ReconciliationRun, ...]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(reconciliation_runs_table).order_by("started_at").limit(limit)
            ).all()
        return tuple(_row_to_run(row) for row in rows)

    # ── Safe mode ─────────────────────────────────────────────────────────
    def get_safe_mode(self) -> SafeModeRecord:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(safe_mode_state_table).where(
                    safe_mode_state_table.c.id == SAFE_MODE_SINGLETON_ID
                )
            ).first()
        if row is None:
            return _empty_safe_mode(_EPOCH)
        return SafeModeRecord.model_validate(
            {
                "active": row.active,
                "since": row.since,
                "reason_codes": tuple(row.reason_codes or ()),
                "note": row.note,
                "exited_at": row.exited_at,
                "updated_at": row.updated_at,
            }
        )

    def set_safe_mode(self, record: SafeModeRecord) -> SafeModeRecord:
        values = {
            "active": record.active,
            "since": record.since,
            "reason_codes": list(record.reason_codes),
            "note": record.note,
            "exited_at": record.exited_at,
            "updated_at": record.updated_at,
        }
        with self._engine.begin() as conn:
            result = conn.execute(
                safe_mode_state_table.update()
                .where(safe_mode_state_table.c.id == SAFE_MODE_SINGLETON_ID)
                .values(**values)
            )
            if result.rowcount != 1:
                conn.execute(
                    safe_mode_state_table.insert().values(id=SAFE_MODE_SINGLETON_ID, **values)
                )
        return record
