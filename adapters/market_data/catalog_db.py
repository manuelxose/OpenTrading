"""SQLAlchemy Core table definitions for the market data catalog.

PostgreSQL is the metadata/catalog/state store (ADR-0010): instruments,
ingestion runs, gold dataset versions + partitions, and detected bar gaps.
Heavy bar data itself lives in Parquet/MinIO (ADR-0011) — these tables only
point at it.

Alembic migration ``0002_market_data_catalog`` mirrors these definitions
(self-contained DDL, per Phase 1 convention); keep both in sync on change.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    Numeric,
    Table,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()

instruments_table = Table(
    "instruments",
    metadata,
    Column("instrument_id", Text, primary_key=True),
    Column("symbol", Text, nullable=False),
    Column("exchange", Text, nullable=False),
    Column("asset_class", Text, nullable=False),
    Column("base_currency", Text, nullable=True),
    Column("quote_currency", Text, nullable=True),
    Column("price_precision", Integer, nullable=False),
    Column("tick_size", Numeric(38, 8), nullable=False),
    Column("lot_size", Numeric(38, 8), nullable=False),
    Column("lot_step", Numeric(38, 8), nullable=False),
    Column("min_lot", Numeric(38, 8), nullable=False),
    Column("max_lot", Numeric(38, 8), nullable=False),
    Column("contract_size", Numeric(38, 8), nullable=False, server_default=text("1")),
    Column("is_active", Boolean, nullable=False, server_default=text("false")),
    Column("source", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

ingestion_runs_table = Table(
    "ingestion_runs",
    metadata,
    Column("run_id", Uuid, primary_key=True),
    Column("source", Text, nullable=False),
    Column("data_class", Text, nullable=False),
    Column("status", Text, nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    Column("stats", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("error", Text, nullable=True),
)

dataset_versions_table = Table(
    "dataset_versions",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("dataset_id", Text, nullable=False),
    Column("version", Integer, nullable=False),
    Column("instrument_id", Text, nullable=False),
    Column("data_class", Text, nullable=False),
    Column("timeframe", Text, nullable=False),
    Column("state", Text, nullable=False),
    Column("dataset_hash", Text, nullable=True),
    Column("row_count", Integer, nullable=False, server_default="0"),
    Column("event_time_min", DateTime(timezone=True), nullable=True),
    Column("event_time_max", DateTime(timezone=True), nullable=True),
    Column("available_time_max", DateTime(timezone=True), nullable=True),
    Column("opened_at", DateTime(timezone=True), nullable=False),
    Column("sealed_at", DateTime(timezone=True), nullable=True),
)

dataset_partitions_table = Table(
    "dataset_partitions",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("dataset_version_id", BigInteger, nullable=False),
    Column("object_key", Text, nullable=False),
    Column("row_count", Integer, nullable=False),
    Column("checksum", Text, nullable=False),
)

bar_gaps_table = Table(
    "bar_gaps",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("ingestion_run_id", Uuid, nullable=False),
    Column("instrument_id", Text, nullable=False),
    Column("timeframe", Text, nullable=False),
    Column("expected_time", DateTime(timezone=True), nullable=False),
    Column("previous_time", DateTime(timezone=True), nullable=False),
    Column("next_time", DateTime(timezone=True), nullable=True),
    Column("detected_at", DateTime(timezone=True), nullable=False),
)
