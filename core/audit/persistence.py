"""Durable PostgreSQL audit sink (architecture §13, migration 0001).

``audit_events`` is the append-only governance trail: rows are written once and
never updated or deleted. ``PostgresAuditSink`` records an :class:`AuditEntry`
as a single row; the unique ``audit_id`` constraint makes duplicate replay a
no-op instead of a corruption.
"""

from __future__ import annotations

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    MetaData,
    Table,
    Text,
    create_engine,
    insert,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUuid
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from core.audit.audit import AuditEntry, AuditSink
from core.config.settings import ensure_psycopg_dsn

__all__ = ["PostgresAuditSink", "audit_events_table"]

_metadata = MetaData()
audit_events_table = Table(
    "audit_events",
    _metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("audit_id", PGUuid(as_uuid=True), nullable=False, unique=True),
    Column("schema_version", Text, nullable=False),
    Column("trace_id", PGUuid(as_uuid=True), nullable=True),
    Column("actor", Text, nullable=False),
    Column("action", Text, nullable=False),
    Column("target", Text, nullable=True),
    Column("outcome", Text, nullable=False),
    Column("timestamp", DateTime(timezone=True), nullable=False),
    Column(
        "metadata",
        JSON().with_variant(JSONB(astext_type=Text()), "postgresql"),
        nullable=False,
    ),
)


class PostgresAuditSink(AuditSink):
    """Append-only PostgreSQL audit sink. Immutable by construction: only
    ``INSERT`` is ever issued against ``audit_events``; replayed ``audit_id``
    values are silently skipped (idempotent recording, INV-6 replay safety).
    """

    def __init__(self, dsn: str, engine: Engine | None = None) -> None:
        self._engine = engine or create_engine(ensure_psycopg_dsn(dsn), pool_pre_ping=True)

    def record(self, entry: AuditEntry) -> None:
        values = {
            "audit_id": entry.audit_id,
            "schema_version": entry.schema_version,
            "trace_id": entry.trace_id,
            "actor": entry.actor,
            "action": entry.action,
            "target": entry.target,
            "outcome": entry.outcome,
            "timestamp": entry.timestamp,
            "metadata": entry.metadata,
        }
        try:
            with self._engine.begin() as conn:
                conn.execute(insert(audit_events_table).values(**values))
        except IntegrityError:
            # Replayed audit id — the original row is already immutable.
            return
