"""Adapter-internal contracts for TradingAgents.

These types exist ONLY at the boundary. The domain (``core/``) never sees them:
what crosses into the domain is the canonical ``ResearchRequest`` /
``MarketSnapshot`` (in) and ``LLMSignal`` (out).

- :class:`AdapterConfig` — explicit, validated configuration (timeout/retry
  budgets, provider/models, debate depth).
- :class:`UpstreamInput` — the request translated to the upstream ``propagate``
  call surface.
- :class:`UpstreamRunResult` — the normalized upstream state, preserving
  analyst / researcher / trader / portfolio-manager evidence.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "AdapterConfig",
    "AssetType",
    "MockScenario",
    "ModelMetadata",
    "TokenUsage",
    "TradingAgentsRating",
    "UpstreamInput",
    "UpstreamRunResult",
]

AssetType = Literal["stock", "crypto"]


class TradingAgentsRating(StrEnum):
    """Upstream 5-tier rating (Research Manager and Portfolio Manager).

    Maps 1:1 onto the canonical ``SignalDirection`` in ``mapper.py``.
    """

    BUY = "Buy"
    OVERWEIGHT = "Overweight"
    HOLD = "Hold"
    UNDERWEIGHT = "Underweight"
    SELL = "Sell"


class AdapterConfig(BaseModel):
    """Explicit configuration for one adapter instance.

    Model choice is mandatory — the adapter never silently inherits upstream
    defaults, so ``model_name`` metadata is always truthful.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    llm_provider: str = Field(min_length=1, description="e.g. openai, anthropic, deepseek")
    deep_think_llm: str = Field(min_length=1, description="Model for complex reasoning")
    quick_think_llm: str = Field(min_length=1, description="Model for quick tasks")
    temperature: float | None = Field(default=None, description="None → provider default")
    max_debate_rounds: int = Field(default=2, ge=1)
    max_risk_discuss_rounds: int = Field(default=2, ge=1)
    llm_max_retries: int = Field(default=2, ge=0, description="Upstream per-call retry budget")
    selected_analysts: tuple[str, ...] = Field(default=("market", "social", "news", "fundamentals"))
    checkpoint_enabled: bool = False
    backend_url: str | None = None

    # Adapter-side budgets (architecture §3: the LLM must never block forever).
    timeout_seconds: float = Field(default=900.0, gt=0)
    retry_max_attempts: int = Field(default=2, ge=1)
    retry_base_delay_seconds: float = Field(default=2.0, ge=0)
    retry_backoff_factor: float = Field(default=2.0, ge=1.0)
    retry_delay_cap_seconds: float = Field(default=30.0, ge=0)

    # Upstream filesystem isolation (defaults avoid writing into $HOME).
    data_cache_dir: Path | None = None
    results_dir: Path | None = None

    # Opaque passthrough for upstream config keys we do not model
    # (e.g. memory_log_path, benchmark_ticker).
    upstream_extra: dict[str, Any] = Field(default_factory=dict)


class TokenUsage(BaseModel):
    """Aggregated token usage for one upstream run (captured when available)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    calls: int = Field(default=0, ge=0)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)


class ModelMetadata(BaseModel):
    """Provider/model/version facts recorded on every signal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1)
    deep_think_llm: str = Field(min_length=1)
    quick_think_llm: str = Field(min_length=1)
    upstream_version: str = Field(min_length=1)
    upstream_version_detected: str | None = None
    prompt_version: str = Field(min_length=1)


class UpstreamInput(BaseModel):
    """A ``ResearchRequest`` (+ optional ``MarketSnapshot``) translated to the
    upstream ``propagate(ticker, trade_date, asset_type)`` call surface.

    ``context_payload`` is the point-in-time context the domain provided (INV-3):
    it is validated to carry nothing posterior to ``as_of`` before this object
    exists, and it travels with the run for auditability.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    ticker: str = Field(min_length=1, description="Upstream symbol (Yahoo format)")
    trade_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    asset_type: AssetType
    as_of: datetime
    context_payload: dict[str, Any] = Field(default_factory=dict)


class UpstreamRunResult(BaseModel):
    """Normalized upstream output with evidence preserved per committee role."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    ticker: str = Field(min_length=1)
    trade_date: str = Field(min_length=1)
    as_of: datetime
    rating: TradingAgentsRating
    decision_markdown: str = Field(min_length=1, description="Portfolio Manager output")
    investment_plan: str = Field(default="", description="Research Manager output")
    trader_plan: str = Field(default="", description="Trader proposal (advisory only)")
    analyst_reports: dict[str, str] = Field(
        default_factory=dict,
        description="fundamentals_report | market_report | sentiment_report | news_report",
    )
    bull_history: str = Field(default="")
    bear_history: str = Field(default="")
    risk_history: str = Field(default="", description="Risk analyst debate history")
    model_metadata: ModelMetadata
    token_usage: TokenUsage | None = None
    cost_usd: float | None = Field(default=None, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    trace_id: UUID | None = None


class MockScenario(BaseModel):
    """Deterministic scenario played back by :class:`MockTradingAgentsAdapter`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str = Field(min_length=1)
    decision_markdown: str = Field(min_length=1)
    rating: TradingAgentsRating | None = Field(
        default=None, description="Defaults to the rating parsed from decision_markdown"
    )
    investment_plan: str = ""
    trader_plan: str = ""
    analyst_reports: dict[str, str] = Field(default_factory=dict)
    bull_history: str = ""
    bear_history: str = ""
    risk_history: str = ""
