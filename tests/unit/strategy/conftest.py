"""Broker-specification fixtures for XAU_RPB strategy tests."""

from __future__ import annotations

import pytest
from research.strategies.xau_rpb import BrokerSpec


@pytest.fixture
def standard_spec() -> BrokerSpec:
    """A plain 2-digit XAUUSD specification (100 oz contract, 0.01 lot step)."""
    return BrokerSpec(
        symbol="XAUUSD",
        point=0.01,
        digits=2,
        tick_value=1.0,
        tick_size=0.01,
        lot_size=100.0,
        min_lot=0.01,
        max_lot=50.0,
        lot_step=0.01,
        stop_level_points=10.0,
        freeze_level_points=0.0,
    )


@pytest.fixture
def three_digit_spec() -> BrokerSpec:
    """A 3-digit broker with a coarser lot step — the portability case."""
    return BrokerSpec(
        symbol="GOLD.a",
        point=0.001,
        digits=3,
        tick_value=0.1,
        tick_size=0.001,
        lot_size=100.0,
        min_lot=0.1,
        max_lot=20.0,
        lot_step=0.1,
        stop_level_points=50.0,
    )
