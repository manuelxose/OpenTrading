"""emergency control system: kill switches and dead man switch state

Revision ID: 0007_emergency_controls
Revises: 0006_live_gated
Create Date: 2026-08-28

Persisted state for the emergency control system (INV-7, architecture §10):

- ``emergency_controls`` — one row per ``(level, target)`` with the four
  levels STRATEGY_KILL / INSTRUMENT_KILL / NO_NEW_POSITIONS / EMERGENCY_KILL;
  deactivations keep the row (``active=false``) so activation history stays
  auditable.
- ``emergency_dead_man`` — the dead man switch singleton: heartbeat timestamps
  and the safe-execution-state flag entered on Core ↔ MT4 heartbeat loss.

Mirrors ``engines/execution/emergency_persistence.py``; keep both in sync.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007_emergency_controls"
down_revision = "0006_live_gated"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "emergency_controls",
        sa.Column("level", sa.Text(), primary_key=True),
        sa.Column("target", sa.Text(), primary_key=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("activated_by", sa.Text(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("deactivated_by", sa.Text(), nullable=True),
        sa.Column("deactivate_reason", sa.Text(), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "emergency_dead_man",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dead_man_switch_enabled", sa.Boolean(), nullable=False),
        sa.Column("heartbeat_timeout_seconds", sa.Float(), nullable=False),
        sa.Column("armed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("safe_execution_state", sa.Boolean(), nullable=False),
        sa.Column("heartbeat_lost_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "reason_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("emergency_dead_man")
    op.drop_table("emergency_controls")
