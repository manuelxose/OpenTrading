"""TradingAgents adapter — Phase 2, read-only LLM committee (ADR-0004, INV-1).

Strict boundary rules:

- ONLY ``adapters/tradingagents/client.py`` imports upstream (lazily). The rest
  of the application never imports ``tradingagents`` classes (enforced by
  ``tests/unit/tradingagents/test_boundary.py`` and the core import guard).
- Input: canonical ``ResearchRequest`` (+ optional ``MarketSnapshot``).
- Output: canonical ``LLMSignal``. Advisory only — never ``OrderIntent``,
  never MT4, never executable position sizing.
- Upstream is pinned: see ``pin.py`` / ``external-lock.yaml``.

Both adapters implement the same :class:`TradingAgentsAdapter` surface, so the
domain pipeline is identical with the live upstream or with the deterministic
mock (that is the boundary contract).
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from core.schemas.market import MarketSnapshot
from core.schemas.research import ResearchRequest
from core.schemas.signals import LLMSignal

from adapters.tradingagents.client import LiveTradingAgentsAdapter, TokenUsageCollector
from adapters.tradingagents.errors import (
    TradingAgentsError,
    TradingAgentsMappingError,
    TradingAgentsTimeoutError,
    TradingAgentsUnavailableError,
    TradingAgentsVersionError,
)
from adapters.tradingagents.evaluator import EvalReport, ScenarioFixture
from adapters.tradingagents.mock import MockTradingAgentsAdapter, default_mock_scenario
from adapters.tradingagents.schemas import (
    AdapterConfig,
    MockScenario,
    ModelMetadata,
    TokenUsage,
    TradingAgentsRating,
    UpstreamInput,
    UpstreamRunResult,
)

__all__ = [
    "AdapterConfig",
    "EvalReport",
    "LiveTradingAgentsAdapter",
    "MockScenario",
    "MockTradingAgentsAdapter",
    "ModelMetadata",
    "ScenarioFixture",
    "TokenUsage",
    "TokenUsageCollector",
    "TradingAgentsAdapter",
    "TradingAgentsError",
    "TradingAgentsMappingError",
    "TradingAgentsRating",
    "TradingAgentsTimeoutError",
    "TradingAgentsUnavailableError",
    "TradingAgentsVersionError",
    "UpstreamInput",
    "UpstreamRunResult",
    "default_mock_scenario",
]


class TradingAgentsAdapter(Protocol):
    """Boundary surface every TradingAgents adapter (live or mock) implements.

    ``run`` is the complete contract: ``ResearchRequest`` (+ optional
    ``MarketSnapshot``) in, ``LLMSignal`` out. Nothing else crosses this line.
    """

    name: str

    def run(
        self,
        request: ResearchRequest,
        snapshot: MarketSnapshot | None = None,
        *,
        trace_id: UUID | None = None,
        now: datetime | None = None,
    ) -> LLMSignal: ...
