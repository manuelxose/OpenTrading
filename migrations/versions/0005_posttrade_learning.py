"""post-trade learning loop: canonical metrics + trade contexts

Revision ID: 0005_posttrade_learning
Revises: 0004_paper_pipeline
Create Date: 2026-08-27

Persistence for the Phase 7 post-trade analysis & learning engine
(architecture §17):

- ``posttrade_reviews`` — one row per closed-and-reconciled trade: every
  canonical metric as a typed column (PnL, fees, slippage, R multiple, alpha,
  MAE/MFE, holding time, efficiencies, prediction error, regime) plus the full
  ``PostTradeReview`` payload as JSONB for reconstruction. Idempotent by
  ``review_id`` (deterministic UUIDv5 over the trade id).
- ``trade_contexts`` — per-trace fragments captured while the trade was live
  (quant / llm / fused / proposal / risk_decision), so a review is complete
  even after a worker restart.

Mirrors ``engines/posttrade/persistence.py`` and
``apps/worker/persistence.py``; keep all three in sync on change.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0005_posttrade_learning"
down_revision = "0004_paper_pipeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "posttrade_reviews",
        sa.Column("review_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("trade_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position_id", sa.Text(), nullable=True),
        sa.Column("instrument_id", sa.Text(), nullable=False),
        sa.Column("strategy_id", sa.Text(), nullable=False),
        sa.Column("strategy_version", sa.Text(), nullable=False),
        sa.Column("direction", sa.Text(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_reason", sa.Text(), nullable=False),
        sa.Column("pnl_gross", sa.Numeric(38, 8), nullable=False),
        sa.Column("pnl_net", sa.Numeric(38, 8), nullable=False),
        sa.Column("fees", sa.Numeric(38, 8), nullable=False),
        sa.Column("slippage", sa.Numeric(38, 8), nullable=False),
        sa.Column("r_multiple", sa.Float(), nullable=True),
        sa.Column("alpha_pct", sa.Float(), nullable=True),
        sa.Column("mae_pct", sa.Float(), nullable=True),
        sa.Column("mfe_pct", sa.Float(), nullable=True),
        sa.Column("holding_seconds", sa.Integer(), nullable=False),
        sa.Column("entry_efficiency", sa.Float(), nullable=True),
        sa.Column("exit_efficiency", sa.Float(), nullable=True),
        sa.Column("prediction_error_pct", sa.Float(), nullable=True),
        sa.Column(
            "signal_calibration_error",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("expected_return_pct", sa.Float(), nullable=True),
        sa.Column("actual_return_pct", sa.Float(), nullable=True),
        sa.Column("benchmark_return_pct", sa.Float(), nullable=True),
        sa.Column("expected_r", sa.Float(), nullable=True),
        sa.Column("market_regime", sa.Text(), nullable=False),
        sa.Column("verdict", sa.Text(), nullable=False),
        sa.Column("postmortem_completed", sa.Boolean(), nullable=False),
        sa.Column(
            "review_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("artifact_key", sa.Text(), nullable=True),
        sa.Column("vault_path", sa.Text(), nullable=True),
        sa.Column("episode_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("schema_version", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_posttrade_reviews_trade_id",
        "posttrade_reviews",
        ["trade_id"],
        unique=False,
    )

    op.create_table(
        "trade_contexts",
        sa.Column("trace_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("instrument_id", sa.Text(), nullable=False),
        sa.Column(
            "fragments",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("trade_contexts")
    op.drop_table("posttrade_reviews")
