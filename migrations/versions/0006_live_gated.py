"""durable LIVE_GATED approvals and kill controls

Revision ID: 0006_live_gated
Revises: 0005_posttrade_learning
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_live_gated"
down_revision = "0005_posttrade_learning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "live_approvals",
        sa.Column("order_intent_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_live_approvals_status", "live_approvals", ["status"])
    op.create_table(
        "live_kill_switches",
        sa.Column("scope", sa.Text(), primary_key=True),
        sa.Column("target", sa.Text(), primary_key=True),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("cleared_by", sa.Text(), nullable=True),
        sa.Column("clear_reason", sa.Text(), nullable=True),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("live_kill_switches")
    op.drop_index("ix_live_approvals_status", table_name="live_approvals")
    op.drop_table("live_approvals")
