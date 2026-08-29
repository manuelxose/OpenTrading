"""durable LIVE_AUTO governance registry and PnL ledger

Revision ID: 0008_live_auto
Revises: 0007_emergency_controls
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_live_auto"
down_revision = "0007_emergency_controls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # LIVE_AUTO registry: the deterministic governance authority over which
    # strategies may trade without per-trade human approval. Rows are written
    # only by the operator-authenticated promotion API and are immutable while
    # active; demotion is recorded in-place with full attribution.
    op.create_table(
        "live_auto_strategies",
        sa.Column("strategy_id", sa.Text(), primary_key=True),
        sa.Column("strategy_version", sa.Text(), nullable=False),
        sa.Column("from_state", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("risk_budget", sa.Numeric(38, 8), nullable=False),
        sa.Column("capital_allocation", sa.Numeric(38, 8), nullable=False),
        sa.Column("promoted_by", sa.Text(), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("demoted_by", sa.Text(), nullable=True),
        sa.Column("demoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("demote_reason", sa.Text(), nullable=True),
    )
    op.create_index("ix_live_auto_strategies_active", "live_auto_strategies", ["active"])

    # Append-only realized-PnL ledger for the global LIVE_AUTO loss limit.
    # Written by the operator-authenticated PnL endpoint (or deterministic
    # posttrade integration); read by the live-auto authorizer on every entry.
    op.create_table(
        "live_auto_pnl_ledger",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ledger_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("strategy_id", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(38, 8), nullable=False),
        sa.Column("recorded_by", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ledger_id"),
    )
    op.create_index("ix_live_auto_pnl_ledger_strategy", "live_auto_pnl_ledger", ["strategy_id"])


def downgrade() -> None:
    op.drop_index("ix_live_auto_pnl_ledger_strategy", table_name="live_auto_pnl_ledger")
    op.drop_table("live_auto_pnl_ledger")
    op.drop_index("ix_live_auto_strategies_active", table_name="live_auto_strategies")
    op.drop_table("live_auto_strategies")
