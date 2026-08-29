"""market data catalog: instruments, ingestion runs, dataset versions, partitions, gaps

Revision ID: 0002_market_data_catalog
Revises: 0001_platform_primitives
Create Date: 2026-08-26

Metadata/state for the market data platform (ADR-0010): the normalized
instrument registry, ingestion run state, immutable gold dataset versions with
their Parquet partitions, and detected bar gaps. Bar data itself stays in
MinIO/Parquet (ADR-0011) — these tables only point at it.

Mirrors ``adapters/market_data/catalog_db.py``; keep both in sync on change.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0002_market_data_catalog"
down_revision = "0001_platform_primitives"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Normalized instrument registry (metadata, not market data).
    op.create_table(
        "instruments",
        sa.Column("instrument_id", sa.Text(), nullable=False),
        sa.Column("symbol", sa.Text(), nullable=False),
        sa.Column("exchange", sa.Text(), nullable=False),
        sa.Column("asset_class", sa.Text(), nullable=False),
        sa.Column("base_currency", sa.Text(), nullable=True),
        sa.Column("quote_currency", sa.Text(), nullable=True),
        sa.Column("price_precision", sa.Integer(), nullable=False),
        sa.Column("tick_size", sa.Numeric(38, 8), nullable=False),
        sa.Column("lot_size", sa.Numeric(38, 8), nullable=False),
        sa.Column("lot_step", sa.Numeric(38, 8), nullable=False),
        sa.Column("min_lot", sa.Numeric(38, 8), nullable=False),
        sa.Column("max_lot", sa.Numeric(38, 8), nullable=False),
        sa.Column("contract_size", sa.Numeric(38, 8), nullable=False, server_default=sa.text("1")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("instrument_id"),
    )

    op.create_table(
        "ingestion_runs",
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("data_class", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "stats",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index("ix_ingestion_runs_source", "ingestion_runs", ["source"], unique=False)

    # Immutable gold dataset versions. state OPEN → SEALED exactly once;
    # sealing stores the deterministic content hash (Phase 1 DoD).
    op.create_table(
        "dataset_versions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("dataset_id", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("instrument_id", sa.Text(), nullable=False),
        sa.Column("data_class", sa.Text(), nullable=False),
        sa.Column("timeframe", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("dataset_hash", sa.Text(), nullable=True),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("event_time_min", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_time_max", sa.DateTime(timezone=True), nullable=True),
        sa.Column("available_time_max", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "version", name="uq_dataset_versions_id_version"),
        sa.UniqueConstraint(
            "instrument_id",
            "timeframe",
            "version",
            name="uq_dataset_versions_instrument_tf_version",
        ),
    )

    op.create_table(
        "dataset_partitions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("dataset_version_id", sa.BigInteger(), nullable=False),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["dataset_version_id"], ["dataset_versions.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_dataset_partitions_version", "dataset_partitions", ["dataset_version_id"], unique=False
    )

    # Missing-bar detections (silver quality engine), per ingestion run.
    op.create_table(
        "bar_gaps",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ingestion_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("instrument_id", sa.Text(), nullable=False),
        sa.Column("timeframe", sa.Text(), nullable=False),
        sa.Column("expected_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["ingestion_run_id"], ["ingestion_runs.run_id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_bar_gaps_run", "bar_gaps", ["ingestion_run_id"], unique=False)
    op.create_index(
        "ix_bar_gaps_instrument", "bar_gaps", ["instrument_id", "timeframe"], unique=False
    )


def downgrade() -> None:
    op.drop_table("bar_gaps")
    op.drop_table("dataset_partitions")
    op.drop_table("dataset_versions")
    op.drop_table("ingestion_runs")
    op.drop_table("instruments")
