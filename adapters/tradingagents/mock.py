"""Deterministic mock TradingAgents adapter (contract tests + evaluation).

Implements exactly the same surface as :class:`LiveTradingAgentsAdapter` and
shares the same mapper, so downstream consumers cannot tell the difference —
except that this adapter imports nothing from upstream, makes no network calls,
costs nothing, and is fully deterministic.

Used to prove the boundary contract: the domain pipeline works whether the real
TradingAgents package is installed or not.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Set
from datetime import datetime
from uuid import UUID

from core.schemas.market import MarketSnapshot
from core.schemas.research import ResearchRequest
from core.schemas.signals import LLMSignal

from adapters.tradingagents import mapper
from adapters.tradingagents.errors import TradingAgentsError
from adapters.tradingagents.pin import UPSTREAM_VERSION
from adapters.tradingagents.schemas import (
    MockScenario,
    ModelMetadata,
    TokenUsage,
    TradingAgentsRating,
    UpstreamRunResult,
)

__all__ = ["MockTradingAgentsAdapter", "default_mock_scenario"]


def default_mock_scenario() -> MockScenario:
    """The built-in fallback: a balanced, evidence-carrying HOLD decision."""
    return MockScenario(
        scenario_id="default-hold",
        rating=TradingAgentsRating.HOLD,
        decision_markdown=(
            "**Rating**: Hold\n\n"
            "**Executive Summary**: Maintain the current position; no action "
            "needed while the bull and bear cases remain balanced.\n\n"
            "**Investment Thesis**: Bullish growth arguments are offset by "
            "valuation and macro risks, leaving no decisive edge either way.\n\n"
            "**Time Horizon**: 1-3 months"
        ),
        investment_plan=(
            "**Recommendation**: Hold\n\n"
            "**Rationale**: Both sides of the debate carry comparable weight.\n\n"
            "**Strategic Actions**: Hold current exposure; reassess on the next "
            "catalyst."
        ),
        trader_plan=(
            "**Action**: Hold\n\n"
            "**Reasoning**: Balanced setup; no edge.\n\n"
            "FINAL TRANSACTION PROPOSAL: **HOLD**"
        ),
        analyst_reports={
            "fundamentals_report": "Fundamentals are solid but priced in; "
            "margins are stable and the balance sheet is healthy.",
            "market_report": "Price action is range-bound near resistance, with no clear trend.",
            "sentiment_report": "Retail and institutional sentiment is mixed.",
            "news_report": "No material catalysts in the recent news flow.",
        },
        bull_history="Bull: growth runway remains intact.",
        bear_history="Bear: valuation is demanding at current multiples.",
        risk_history=(
            "Aggressive: lean into the trend. Conservative: trim on strength. "
            "Neutral: balanced sizing."
        ),
    )


class MockTradingAgentsAdapter:
    """Scenario-driven stand-in for the upstream committee.

    Scenario lookup: exact ``ticker`` first, then ``ticker@trade_date``, then
    the default scenario. Instruments listed in ``fail_for`` raise a
    :class:`TradingAgentsError` to exercise fail-safe paths in tests.
    """

    name = "tradingagents-mock"

    def __init__(
        self,
        scenarios: Mapping[str, MockScenario] | None = None,
        *,
        default: MockScenario | None = None,
        fail_for: Set[str] = frozenset(),
        latency_ms: int = 25,
        cost_usd: float = 0.001,
        provider: str = "mock-provider",
        deep_model: str = "mock-deep-model",
        quick_model: str = "mock-quick-model",
        clock_now: Callable[[], datetime] | None = None,
    ) -> None:
        self._scenarios = dict(scenarios or {})
        self._default = default or default_mock_scenario()
        self._fail_for = fail_for
        self._latency_ms = latency_ms
        self._cost_usd = cost_usd
        self._provider = provider
        self._deep_model = deep_model
        self._quick_model = quick_model
        self._clock_now = clock_now or mapper.now_utc

    def run(
        self,
        request: ResearchRequest,
        snapshot: MarketSnapshot | None = None,
        *,
        trace_id: UUID | None = None,
        now: datetime | None = None,
    ) -> LLMSignal:
        """Play back the matched scenario through the same mapper as the live
        adapter, so the boundary contract is exercised identically."""
        produced_at = now or self._clock_now()
        upstream_input = mapper.request_to_upstream_input(request, snapshot)

        if upstream_input.ticker in self._fail_for:
            raise TradingAgentsError(f"mock failure injected for {upstream_input.ticker!r}")

        scenario = (
            self._scenarios.get(upstream_input.ticker)
            or self._scenarios.get(f"{upstream_input.ticker}@{upstream_input.trade_date}")
            or self._default
        )
        rating = scenario.rating or mapper.parse_rating(scenario.decision_markdown)
        metadata = ModelMetadata(
            provider=self._provider,
            deep_think_llm=self._deep_model,
            quick_think_llm=self._quick_model,
            upstream_version=UPSTREAM_VERSION,
            upstream_version_detected=UPSTREAM_VERSION,
            prompt_version=mapper.PROMPT_VERSION,
        )
        result = UpstreamRunResult(
            ticker=upstream_input.ticker,
            trade_date=upstream_input.trade_date,
            as_of=upstream_input.as_of,
            rating=rating,
            decision_markdown=scenario.decision_markdown,
            investment_plan=scenario.investment_plan,
            trader_plan=scenario.trader_plan,
            analyst_reports=scenario.analyst_reports,
            bull_history=scenario.bull_history,
            bear_history=scenario.bear_history,
            risk_history=scenario.risk_history,
            model_metadata=metadata,
            token_usage=TokenUsage(calls=12, prompt_tokens=4800, completion_tokens=1600),
            cost_usd=self._cost_usd,
            latency_ms=self._latency_ms,
            trace_id=trace_id,
        )
        return mapper.result_to_signal(
            result, request=request, snapshot=snapshot, trace_id=trace_id, produced_at=produced_at
        )
