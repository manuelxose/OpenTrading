"""execution state: orders, positions, reconciliation runs, safe mode

Revision ID: 0003_execution_state
Revises: 0002_market_data_catalog
Create Date: 2026-08-26

Authoritative persisted execution state for broker reconciliation and Safe Mode
(INV-6, architecture §9, ADR-0021):

- ``execution_orders``     — one row per ``order_intent_id`` (INV-2 idempotency
  key); ``version`` guarded by compare-and-set in the store layer.
- ``execution_positions``  — broker-side positions linked to their intent.
- ``reconciliation_runs``  — every mandatory reconciliation pass + JSONB
  discrepancies.
- ``safe_mode_state``      — the SAFE_MODE singleton row.

Mirrors ``engines/execution/persistence.py``; keep both in sync on change.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0003_execution_state"
down_revision = "0002_market_data_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "execution_orders",
        sa.Column("order_intent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("strategy_id", sa.Text(), nullable=False),
        sa.Column("strategy_version", sa.Text(), nullable=False),
        sa.Column("instrument_id", sa.Text(), nullable=False),
        sa.Column("venue", sa.Text(), nullable=True),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column("order_type", sa.Text(), nullable=False),
        sa.Column("requested_quantity", sa.Numeric(38, 8), nullable=False),
        sa.Column("filled_quantity", sa.Numeric(38, 8), nullable=False),
        sa.Column("remaining_quantity", sa.Numeric(38, 8), nullable=False),
        sa.Column("average_fill_price", sa.Numeric(38, 8), nullable=True),
        sa.Column("venue_order_id", sa.Text(), nullable=True),
        sa.Column("venue_position_id", sa.Text(), nullable=True),
        sa.Column("commission", sa.Numeric(38, 8), nullable=False, server_default=sa.text("0")),
        sa.Column("fees", sa.Numeric(38, 8), nullable=False, server_default=sa.text("0")),
        sa.Column("slippage", sa.Numeric(38, 8), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("last_event_sequence", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "processed_event_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reconciliation_note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("order_intent_id"),
    )
    op.create_index("ix_execution_orders_state", "execution_orders", ["state"], unique=False)

    op.create_table(
        "execution_positions",
        sa.Column("venue_position_id", sa.Text(), nullable=False),
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("instrument_id", sa.Text(), nullable=False),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Numeric(38, 8), nullable=False),
        sa.Column("average_entry_price", sa.Numeric(38, 8), nullable=False),
        sa.Column("order_intent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("venue_position_id"),
    )

    op.create_table(
        "reconciliation_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("compared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("broker_reachable", sa.Boolean(), nullable=False),
        sa.Column("broker_connected", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("trading_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("account", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "discrepancies",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "material_discrepancies", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column("orders_reconciled", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("orders_resolved", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("positions_adopted", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("positions_closed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "safe_mode_entered", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "safe_mode_exited", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column(
            "last_sequences",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.PrimaryKeyConstraint("run_id"),
    )

    op.create_table(
        "safe_mode_state",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("since", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "reason_codes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("exited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("safe_mode_state")
    op.drop_table("reconciliation_runs")
    op.drop_table("execution_positions")
    op.drop_index("ix_execution_orders_state", table_name="execution_orders")
    op.drop_table("execution_orders")
