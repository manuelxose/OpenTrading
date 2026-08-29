"""Runtime configuration (pydantic-settings).

Environment variables use the ``OT_`` prefix (see ``.env.example``). Secrets are never
committed and never read from anything but the environment / ``.env`` (INV-9).
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.domain.enums import OperatingMode
from core.schemas.base import SCHEMA_VERSION

__all__ = ["Settings", "get_settings"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OT_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "opentrading-core"
    environment: str = "development"
    operating_mode: OperatingMode = OperatingMode.RESEARCH
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    audit_enabled: bool = True
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    schema_version: str = SCHEMA_VERSION

    # LIVE_GATED is fail-closed: both secrets are mandatory before the API mounts
    # mutation routes. Production injects them from the process secret store.
    live_approval_signing_key: SecretStr | None = None
    live_operator_token: SecretStr | None = None
    live_broker_demo: bool = False
    live_max_quantity: Decimal | None = None
    live_approval_ttl_seconds: int = 30
    live_max_price_drift_bps: Decimal = Decimal("10")
    live_max_quote_age_seconds: int = 5

    # ── LIVE_AUTO (Phase 11) — DISABLED BY DEFAULT ─────────────────────────
    # LIVE_AUTO lets strategies in the LIVE_AUTO lifecycle state trade without
    # per-trade human approval, constrained by deterministic governance (the
    # live-auto registry + the mandatory Risk Engine + emergency controls).
    # Enabling it is an explicit operational decision; promotion of any
    # strategy additionally requires an authenticated operator action that
    # writes an immutable audit event.
    live_auto_enabled: bool = False
    # Hard ceilings enforced at promotion and on every submission:
    live_auto_max_strategies: int = 0
    live_auto_max_capital: Decimal | None = None
    live_auto_max_loss: Decimal | None = None
    # Optional per-strategy risk-budget ceilings (account currency). When the
    # map contains a strategy, its promotion budget may not exceed this value.
    live_auto_strategy_risk_budgets: dict[str, Decimal] = {}

    # ── Emergency control system (INV-7, architecture §10) ─────────────────
    # Dead man switch over the Core ↔ MT4 heartbeat: loss blocks new entries,
    # leaves broker-side SL/TP untouched and raises a CRITICAL alert. Flattening
    # is explicit opt-in only — connectivity loss never auto-closes positions.
    emergency_dead_man_enabled: bool = True
    emergency_heartbeat_timeout_seconds: float = 6.0
    emergency_cancel_pending_on_kill: bool = True
    emergency_flatten_on_kill: bool = False
    emergency_flatten_on_heartbeat_loss: bool = False

    @field_validator("live_operator_token", "live_approval_signing_key")
    @classmethod
    def _live_secrets_must_be_strong(cls, value: SecretStr | None) -> SecretStr | None:
        """Live-mode secrets must be at least 32 characters: an empty or weak
        operator token would otherwise admit ``Authorization: Bearer `` and a
        weak signing key would weaken the HMAC approval signatures (ADR-0025)."""
        if value is not None and len(value.get_secret_value()) < 32:
            raise ValueError(
                "live-mode secrets (OT_LIVE_OPERATOR_TOKEN / "
                "OT_LIVE_APPROVAL_SIGNING_KEY) must be at least 32 characters"
            )
        return value

    # Infrastructure endpoints for readiness checks (GET /readyz).
    # Defaults match infra/compose/docker-compose.yml dev placeholders.
    postgres_dsn: str = "postgresql://opentrading:opentrading-dev@127.0.0.1:5432/opentrading"
    # DDL-capable role for Alembic migrations (ADR-0025 least privilege).
    # When unset (dev), migrations reuse ``postgres_dsn``; production sets this
    # to the ``ot_migrator`` role and leaves ``postgres_dsn`` as the DML-only
    # ``ot_app`` role.
    postgres_migrator_dsn: str | None = None
    redis_url: str = "redis://:opentrading-dev@127.0.0.1:6379/0"
    falkordb_url: str = "redis://:falkordb-dev@127.0.0.1:6380/0"
    minio_endpoint: str = "127.0.0.1:9000"
    minio_access_key: str = "opentrading"
    minio_secret_key: str = "opentrading-dev"
    minio_secure: bool = False
    minio_readiness_bucket: str = "raw"
    readiness_timeout_seconds: float = 2.0

    # Market data platform (Phase 1): staleness threshold for the silver
    # quality engine — bars whose available_time lags the clock by more than
    # this get the STALE quality flag.
    market_data_stale_after_seconds: float = 3600.0

    # ── Autonomous PAPER pipeline (Phase 7, apps/worker) ──────────────────────
    paper_mode_enabled: bool = False
    paper_instruments: str = "EURUSD"  # comma-separated watchlist
    paper_cycle_interval_seconds: int = 300
    paper_llm_enabled: bool = True
    paper_llm_required: bool = False  # False: a failed LLM never blocks the cycle
    paper_llm_timeout_seconds: float = 300.0
    paper_starting_balance: Decimal = Decimal("100000")
    paper_position_equity_pct: Decimal = Decimal("0.02")
    paper_slippage_ticks: int = 1
    paper_commission_bps: Decimal = Decimal("0.5")
    paper_stop_atr_ratio: Decimal = Decimal("1.5")
    paper_take_atr_ratio: Decimal = Decimal("3")
    paper_redis_stream: str = "opentrading:events"
    paper_consumer_group_prefix: str = "opentrading-workers"
    paper_consumer_name: str = "worker-1"
    paper_max_deliveries: int = 5
    paper_block_ms: int = 2000
    paper_batch_size: int = 10
    paper_bus_retry_base_seconds: float = 1.0
    paper_bus_retry_max_seconds: float = 30.0

    # ── Post-trade analysis & learning engine (Phase 7) ───────────────────────
    posttrade_vault_path: str = "vault-trading"
    posttrade_artifact_bucket: str = "posttrade-artifacts"


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings singleton."""
    return Settings()


def ensure_psycopg_dsn(dsn: str) -> str:
    """Force the psycopg (v3) SQLAlchemy dialect on PostgreSQL DSNs.

    The project pins ``psycopg[binary]>=3.2``; a bare ``postgresql://`` URL
    would make SQLAlchemy try the uninstalled psycopg2 dialect. Used by the
    market data catalog and Alembic.
    """
    if dsn.startswith("postgresql://") or dsn.startswith("postgres://"):
        return dsn.replace("postgresql://", "postgresql+psycopg://", 1).replace(
            "postgres://", "postgresql+psycopg://", 1
        )
    return dsn
