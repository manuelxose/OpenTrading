"""Fixtures for leakage tests (INV-3): a small deterministic backtest config."""

from __future__ import annotations

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

from factories import FIXED_START, make_instrument


def make_config() -> BacktestConfig:
    return BacktestConfig(
        instrument=make_instrument(FIXED_START),
        dataset=DatasetConfig(seed=42, n_bars=120),
        spread=SpreadConfig(half_spread_ticks=1),
        slippage=SlippageConfig(fixed_ticks=1, random_min_ticks=0, random_max_ticks=0),
        commission=CommissionConfig(rate_bps=Decimal("1"), min_amount=Decimal("0")),
        rejection=RejectionConfig(probability=0.0),
        baseline=BaselineSmaConfig(fast_window=5, slow_window=20, quantity=Decimal("100000")),
        seed=42,
    )


@pytest.fixture
def config() -> BacktestConfig:
    return make_config()
