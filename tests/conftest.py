"""Shared pytest fixtures."""

from __future__ import annotations

from datetime import datetime

import pytest
from core.clock.clocks import VirtualClock

from factories import FIXED_START


@pytest.fixture
def fixed_start() -> datetime:
    return FIXED_START


@pytest.fixture
def clock(fixed_start: datetime) -> VirtualClock:
    return VirtualClock(fixed_start)
