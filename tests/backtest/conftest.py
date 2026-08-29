"""Shared fixtures for the Nautilus backtest suite (Phase 4 DoD tests)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from adapters.nautilus.config import (
    BacktestConfig,
    BaselineSmaConfig,
    CommissionConfig,
    DatasetConfig,
    RejectionConfig,
    SlippageConfig,
    SpreadConfig,
)
from adapters.nautilus.engine import NautilusBacktestRunner
from adapters.nautilus.results import BacktestRunResult

from factories import FIXED_START, make_instrument


def make_config(**overrides: object) -> BacktestConfig:
    """A realistic cost-inclusive deterministic config; override any field."""
    base: dict[str, object] = {
        "instrument": make_instrument(FIXED_START),
        "dataset": DatasetConfig(seed=42, n_bars=120),
        "spread": SpreadConfig(half_spread_ticks=1),
        "slippage": SlippageConfig(fixed_ticks=1, random_min_ticks=0, random_max_ticks=0),
        "commission": CommissionConfig(rate_bps=Decimal("1"), min_amount=Decimal("0")),
        "rejection": RejectionConfig(probability=0.0),
        "baseline": BaselineSmaConfig(fast_window=5, slow_window=20, quantity=Decimal("100000")),
        "seed": 42,
    }
    base.update(overrides)
    return BacktestConfig(**base)


@pytest.fixture
def config() -> BacktestConfig:
    return make_config()


@pytest.fixture
def runner(config: BacktestConfig) -> NautilusBacktestRunner:
    return NautilusBacktestRunner(config)


@pytest.fixture(scope="module")
def run_result() -> BacktestRunResult:
    """One full baseline run shared by the cost/accounting/metrics assertions."""
    return NautilusBacktestRunner(make_config()).run()


@pytest.fixture
def fixed_start() -> datetime:
    return FIXED_START
