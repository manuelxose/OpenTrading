"""Strategy Lab persistence: M1 bars and evaluated parameter candidates

Revision ID: 0010_strategy_lab
Revises: 0009_audit_trail_immutability

The Strategy Lab is the OFFLINE self-improvement loop (INV-8): the live
supervisor persists one-minute bars (write-only, upserted), and the lab
replays deterministic parameter candidates over them, storing an immutable
evaluation record per candidate. Nothing in the lab can change live risk
settings or promote a strategy — promotions remain operator-audited.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "0010_strategy_lab"
down_revision = "0009_audit_trail_immutability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "strategy_lab_bars",
        sa.Column("instrument_id", sa.Text(), nullable=False),
        sa.Column("minute", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(38, 8), nullable=False),
        sa.Column("high", sa.Numeric(38, 8), nullable=False),
        sa.Column("low", sa.Numeric(38, 8), nullable=False),
        sa.Column("close", sa.Numeric(38, 8), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("instrument_id", "minute"),
    )
    op.create_table(
        "strategy_candidates",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.Text(), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("score", sa.Numeric(38, 8), nullable=False),
        sa.Column("profit_factor", sa.Numeric(38, 8), nullable=False),
        sa.Column("expectancy", sa.Numeric(38, 8), nullable=False),
        sa.Column("trades", sa.Integer(), nullable=False),
        sa.Column("bars", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("candidate_id"),
    )


def downgrade() -> None:
    op.drop_table("strategy_candidates")
    op.drop_table("strategy_lab_bars")
