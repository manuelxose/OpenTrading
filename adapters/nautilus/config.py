"""Backtest configuration for the NautilusTrader adapter (ADR-0007, Phase 4).

The configuration is a plain pydantic model and must serialize canonically so that
``BacktestConfig.config_hash()`` is byte-identical across processes and runs. Every
randomness source in the whole backtest (dataset generation, fill slippage, simulated
rejections) is derived from ``seed`` — never from ``random``/``uuid`` module state.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Self

from core.schemas import Instrument
from pydantic import BaseModel, Field, model_validator

__all__ = [
    "BacktestConfig",
    "BaselineSmaConfig",
    "CommissionConfig",
    "DatasetConfig",
    "RejectionConfig",
    "SlippageConfig",
    "SpreadConfig",
]


class DatasetConfig(BaseModel):
    """Deterministic historical dataset: synthetic (seeded) or parquet replay."""

    source: Literal["synthetic", "parquet"] = "synthetic"
    path: Path | None = Field(default=None, description="Parquet file path when source='parquet'")
    seed: int = 42
    instrument_id: str = Field(default="EURUSD", min_length=1)
    start_time_iso: str = Field(default="2026-01-05T00:00:00Z")
    n_bars: int = Field(default=600, ge=2)
    interval_seconds: int = Field(default=60, ge=1)
    initial_mid: Decimal = Field(default=Decimal("1.08000"), gt=0)
    annual_vol: float = Field(default=0.10, gt=0, le=5)
    drift: float = 0.0


class SpreadConfig(BaseModel):
    """Constant spread applied around each bar close when synthesizing quotes."""

    half_spread_ticks: int = Field(default=1, ge=0, le=100000)


class SlippageConfig(BaseModel):
    """Adverse slippage applied to fills via the simulated order book.

    ``fixed_ticks`` is always applied. ``random_min_ticks``..``random_max_ticks``
    adds a uniformly drawn number of extra ticks from a seed-derived RNG; both zero
    disables the random component entirely.
    """

    fixed_ticks: int = Field(default=0, ge=0)
    random_min_ticks: int = Field(default=0, ge=0)
    random_max_ticks: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _check_random_range(self) -> Self:
        if self.random_max_ticks < self.random_min_ticks:
            raise ValueError("random_max_ticks must be >= random_min_ticks")
        return self


class CommissionConfig(BaseModel):
    """Realistic commission: bps of notional per fill, with a floor in quote currency."""

    rate_bps: Decimal = Field(default=Decimal("0.5"), ge=0)
    min_amount: Decimal = Field(default=Decimal("0"), ge=0)


class RejectionConfig(BaseModel):
    """Simulated venue order rejection (deterministic, seed-derived where random)."""

    probability: float = Field(default=0.0, ge=0, le=1)
    seed_offset: int = 0
    enforce_lot_rules: bool = True
    enforce_price_guard: bool = True
    enforce_market_hours: bool = True


class BaselineSmaConfig(BaseModel):
    """Minimal deterministic baseline strategy: SMA crossover, long-only, market orders."""

    fast_window: int = Field(default=5, ge=1)
    slow_window: int = Field(default=20, ge=2)
    quantity: Decimal = Field(default=Decimal("100000"), gt=0)
    exit_at_end: bool = True
    intent_namespace: str = Field(
        default="25d29a37-0000-4b00-9d7e-000000000007",
        description="UUID namespace for deterministic order_intent_id generation",
    )

    @model_validator(mode="after")
    def _check_windows(self) -> Self:
        if self.slow_window <= self.fast_window:
            raise ValueError("slow_window must be > fast_window")
        return self


class BacktestConfig(BaseModel):
    """Everything needed to reproduce one BACKTEST run exactly (ADR-0007 DoD)."""

    trader_id: str = Field(default="BACKTESTER-001", min_length=1)
    venue_name: str = Field(default="SIM", min_length=1)
    account_currency: str = Field(default="USD", min_length=3, max_length=4)
    starting_balance: Decimal = Field(default=Decimal("1000000"), gt=0)
    seed: int = 42
    instrument: Instrument
    dataset: DatasetConfig = Field(default_factory=DatasetConfig)
    spread: SpreadConfig = Field(default_factory=SpreadConfig)
    slippage: SlippageConfig = Field(default_factory=SlippageConfig)
    commission: CommissionConfig = Field(default_factory=CommissionConfig)
    rejection: RejectionConfig = Field(default_factory=RejectionConfig)
    prob_fill_on_limit: float = Field(default=1.0, ge=0, le=1)
    prob_fill_on_stop: float = Field(default=1.0, ge=0, le=1)
    baseline: BaselineSmaConfig = Field(default_factory=BaselineSmaConfig)

    def config_hash(self) -> str:
        """Stable sha256 over the configuration, insensitive to provenance timestamps."""
        payload: dict[str, Any] = self.model_dump(mode="json")
        instrument_payload = payload["instrument"]
        if isinstance(instrument_payload, dict):
            instrument_payload.pop("produced_at", None)
            instrument_payload.pop("provenance", None)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def start_time(self) -> datetime:
        return datetime.fromisoformat(self.dataset.start_time_iso)
