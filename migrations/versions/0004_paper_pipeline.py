"""autonomous paper pipeline: run ledger, trade lifecycles, paper account

Revision ID: 0004_paper_pipeline
Revises: 0003_execution_state
Create Date: 2026-08-27

Persistence for the Phase 7 autonomous PAPER pipeline (architecture §32 Fase 7):

- ``pipeline_runs``     — the stage idempotency ledger, one row per
  (trace_id, stage); workers skip succeeded stages on redelivery.
- ``trade_lifecycles``  — high-level lifecycle per trace (research → proposal →
  risk → order → position → outcome → review), CAS-guarded by ``version``.
- ``paper_accounts``    — the authoritative paper account (only deterministic
  execution outcomes update it; INV-1, INV-4).

Mirrors ``apps/worker/persistence.py``; keep both in sync on change.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0004_paper_pipeline"
down_revision = "0003_execution_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("cycle_id", sa.Text(), nullable=False),
        sa.Column("instrument_id", sa.Text(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "input_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "output_refs",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index(
        "ix_pipeline_runs_trace_stage",
        "pipeline_runs",
        ["trace_id", "stage"],
        unique=False,
    )

    op.create_table(
        "trade_lifecycles",
        sa.Column("lifecycle_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("proposal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("strategy_id", sa.Text(), nullable=False),
        sa.Column("strategy_version", sa.Text(), nullable=False),
        sa.Column("instrument_id", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("direction", sa.Text(), nullable=True),
        sa.Column("risk_decision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("order_intent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("position_id", sa.Text(), nullable=True),
        sa.Column("trade_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("stop_loss", sa.Numeric(38, 8), nullable=True),
        sa.Column("take_profit", sa.Numeric(38, 8), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_trade_lifecycles_trace_id",
        "trade_lifecycles",
        ["trace_id"],
        unique=False,
    )
    op.create_index(
        "ix_trade_lifecycles_position_id",
        "trade_lifecycles",
        ["position_id"],
        unique=False,
    )

    op.create_table(
        "paper_accounts",
        sa.Column("account_id", sa.Text(), primary_key=True),
        sa.Column("currency", sa.Text(), nullable=False),
        sa.Column("balance", sa.Numeric(38, 8), nullable=False),
        sa.Column("equity", sa.Numeric(38, 8), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(38, 8), nullable=False),
        sa.Column("daily_pnl", sa.Numeric(38, 8), nullable=False),
        sa.Column("peak_equity", sa.Numeric(38, 8), nullable=False),
        sa.Column("consecutive_losses", sa.Integer(), nullable=False),
        sa.Column("last_loss_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("open_positions", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("paper_accounts")
    op.drop_table("trade_lifecycles")
    op.drop_table("pipeline_runs")
