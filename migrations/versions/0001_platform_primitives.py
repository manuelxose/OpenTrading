"""platform primitives: system_events + audit_events

Revision ID: 0001_platform_primitives
Revises:
Create Date: 2026-08-26

Only platform-level tables (architecture §13: the transactional set includes
``system_events`` and ``audit_events``). Business-logic tables (accounts,
strategies, orders, …) arrive with their own phases and migrations — nothing
here anticipates trading semantics.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001_platform_primitives"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # TimescaleDB backs time-series transactional data (ADR-0010). Idempotent:
    # the postgres init script may already have created it.
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    # Append-only platform event log — one row per DomainEvent envelope (§14).
    # The primary key includes event_time because TimescaleDB requires the
    # partition column in unique constraints.
    op.create_table(
        "system_events",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_name", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("producer", sa.Text(), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("event_id", "event_time"),
    )
    op.execute("SELECT create_hypertable('system_events', 'event_time', if_not_exists => TRUE)")
    op.create_index("ix_system_events_event_name", "system_events", ["event_name"], unique=False)

    # Immutable governance trail (core/audit).
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target", sa.Text(), nullable=True),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("audit_id"),
    )
    op.create_index("ix_audit_events_timestamp", "audit_events", ["timestamp"], unique=False)
    op.create_index("ix_audit_events_actor", "audit_events", ["actor"], unique=False)


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("system_events")
    # The timescaledb extension is intentionally left installed: it is shared
    # and idempotent; dropping it would break other databases in the cluster.
