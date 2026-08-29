"""Shared helpers for the TradingAgents adapter unit tests."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, ClassVar
from uuid import uuid4

from core.schemas.research import ResearchRequest

from factories import provenance


def build_research_request(
    t: datetime, *, instrument: str = "NVDA", **context: Any
) -> ResearchRequest:
    """A valid ResearchRequest whose instrument/as_of live in ``context``."""
    ctx: dict[str, Any] = {"instrument_id": instrument}
    ctx.update(context)
    return ResearchRequest(
        request_id=uuid4(),
        title="unit research request",
        question="should we act on this instrument?",
        hypotheses=["hypothesis A", "hypothesis B"],
        requested_by="unit-test",
        context=ctx,
        produced_at=t,
        provenance=provenance(t),
    )


def fake_state(ticker: str = "NVDA", trade_date: str = "2024-05-10") -> dict[str, Any]:
    """A full upstream final state dict shaped like TradingAgents v0.3.1."""
    return {
        "messages": [],
        "company_of_interest": ticker,
        "asset_type": "stock",
        "trade_date": trade_date,
        "instrument_context": f"{ticker} is a company.",
        "past_context": "",
        "investment_debate_state": {
            "bull_history": "Bull: growth runway is intact.",
            "bear_history": "Bear: valuation is demanding.",
            "history": "Debate history.",
            "current_response": "",
            "judge_decision": "",
            "count": 1,
        },
        "risk_debate_state": {
            "aggressive_history": "Aggressive: lean in.",
            "conservative_history": "Conservative: trim.",
            "neutral_history": "Neutral: balanced.",
            "history": "Aggressive: lean in. Conservative: trim. Neutral: balanced.",
            "latest_speaker": "Judge",
            "judge_decision": "",
            "count": 1,
        },
        "market_report": "Uptrend intact with strong momentum.",
        "fundamentals_report": "Revenue growing with expanding margins.",
        "sentiment_report": "Sentiment is bullish.",
        "news_report": "Positive catalysts dominate the flow.",
        "investment_plan": "**Recommendation**: Buy\n\n**Rationale**: Bull case wins.\n\n"
        "**Strategic Actions**: Build position.",
        "trader_investment_plan": "**Action**: Buy\n\n**Reasoning**: Strong setup.\n\n"
        "FINAL TRANSACTION PROPOSAL: **BUY**",
        "final_trade_decision": "**Rating**: Buy\n\n**Executive Summary**: Build position.\n\n"
        "**Investment Thesis**: Growth persists.\n\n**Price Target**: 100.0\n\n"
        "**Time Horizon**: 3-6 months",
    }


class FakeResponse:
    """Duck-typed LangChain generation result carrying token usage."""

    def __init__(
        self,
        usage: dict[str, Any] | None = None,
        usage_metadata: dict[str, Any] | None = None,
    ) -> None:
        self.llm_output: dict[str, Any] = {"token_usage": usage} if usage else {}
        self.usage_metadata = usage_metadata


class FakeGraph:
    """Drop-in replacement for ``TradingAgentsGraph`` (no upstream imports).

    Class-level controls for tests: ``next_queues`` hands each new instance its
    propagate queue (results or exceptions, in order), ``sleep_seconds`` makes
    propagate block (timeout-budget tests), ``instances`` records construction.
    """

    instances: ClassVar[list[FakeGraph]] = []
    next_queues: ClassVar[list[list[Any]]] = []
    sleep_seconds: ClassVar[float] = 0.0

    def __init__(
        self,
        selected_analysts: Any = ("market", "social", "news", "fundamentals"),
        debug: bool = False,
        config: dict[str, Any] | None = None,
        callbacks: list[Any] | None = None,
    ) -> None:
        self.selected_analysts = selected_analysts
        self.debug = debug
        self.config = config or {}
        self.callbacks = list(callbacks or [])
        self.propagate_calls: list[tuple[str, str, str]] = []
        self.propagate_queue = FakeGraph.next_queues.pop(0) if FakeGraph.next_queues else []
        FakeGraph.instances.append(self)

    @classmethod
    def reset(cls) -> None:
        cls.instances.clear()
        cls.next_queues.clear()
        cls.sleep_seconds = 0.0

    def fire_usage(self, usage: dict[str, Any] | None = None) -> None:
        for callback in self.callbacks:
            if hasattr(callback, "on_llm_end"):
                callback.on_llm_end(
                    FakeResponse(
                        usage=usage
                        or {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}
                    )
                )

    def propagate(self, ticker: str, trade_date: str, asset_type: str = "stock") -> Any:
        self.propagate_calls.append((ticker, trade_date, asset_type))
        if FakeGraph.sleep_seconds > 0:
            time.sleep(FakeGraph.sleep_seconds)
        item = self.propagate_queue.pop(0) if self.propagate_queue else None
        if isinstance(item, BaseException):
            raise item
        if item is not None:
            return item
        self.fire_usage()
        return fake_state(ticker, trade_date), "Buy"
