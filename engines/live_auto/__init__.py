"""LIVE_AUTO governance (Phase 11): deterministic, operator-controlled promotion
and fail-closed auto-execution authorization. Disabled by default.

This package is deliberately independent of every LLM, strategy and research
process. It imports nothing from TradingAgents, strategy engines, research
pipelines or any LLM boundary — the same containment guarantee the emergency
control system carries (INV-7). Strategy code cannot reach it; only the
operator-authenticated API promotes strategies, and every promotion writes an
immutable audit event.
"""

from engines.live_auto.config import LiveAutoConfig, LiveAutoViolation
from engines.live_auto.persistence import PostgresLiveAutoStore
from engines.live_auto.registry import (
    InMemoryLiveAutoStore,
    LiveAutoRegistry,
    LiveAutoStore,
    LiveAutoStrategyRecord,
)

__all__ = [
    "InMemoryLiveAutoStore",
    "LiveAutoConfig",
    "LiveAutoRegistry",
    "LiveAutoStore",
    "LiveAutoStrategyRecord",
    "LiveAutoViolation",
    "PostgresLiveAutoStore",
]
