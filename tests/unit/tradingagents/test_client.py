"""Unit tests: live adapter fail-safe, timeout/retry budgets, pin enforcement."""

from __future__ import annotations

import pytest
from adapters.tradingagents import client
from adapters.tradingagents.errors import (
    TradingAgentsError,
    TradingAgentsMappingError,
    TradingAgentsTimeoutError,
    TradingAgentsUnavailableError,
    TradingAgentsVersionError,
)
from adapters.tradingagents.schemas import AdapterConfig
from core.domain.enums import SignalDirection
from core.schemas.signals import LLMSignal
from ta_test_helpers import FakeGraph, FakeResponse, build_research_request, fake_state

from factories import FIXED_START, make_market_snapshot


@pytest.fixture
def config() -> AdapterConfig:
    return AdapterConfig(
        llm_provider="fake",
        deep_think_llm="deep-x",
        quick_think_llm="quick-x",
        timeout_seconds=5.0,
        retry_max_attempts=2,
        retry_base_delay_seconds=0.0,
    )


@pytest.fixture
def fake_upstream(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeGraph.reset()
    monkeypatch.setattr(client, "_load_graph_class", lambda: FakeGraph)
    monkeypatch.setattr(client, "_installed_version", lambda: "0.3.1")


def test_run_end_to_end_with_fake_upstream(config: AdapterConfig, fake_upstream: None) -> None:
    snapshot = make_market_snapshot(FIXED_START, instrument_id="NVDA")
    request = build_research_request(FIXED_START, instrument="NVDA")
    adapter = client.LiveTradingAgentsAdapter(config)
    signal = adapter.run(request, snapshot, now=FIXED_START)
    assert isinstance(signal, LLMSignal)
    assert signal.direction is SignalDirection.LONG
    assert signal.reasoning.startswith("**Rating**: Buy")
    assert signal.as_of == FIXED_START
    (graph,) = FakeGraph.instances
    assert graph.propagate_calls == [("NVDA", "2026-01-05", "stock")]
    # token usage captured from the fake callback payload
    assert adapter.last_result is not None
    assert adapter.last_result.token_usage is not None
    assert adapter.last_result.token_usage.prompt_tokens == 100
    assert adapter.last_result.token_usage.completion_tokens == 50
    assert adapter.last_result.model_metadata.upstream_version_detected == "0.3.1"


def test_upstream_missing_fails_safely(
    config: AdapterConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(client, "_load_graph_class", _raise_import_error)
    monkeypatch.setattr(client, "_installed_version", lambda: None)
    snapshot = make_market_snapshot(FIXED_START, instrument_id="NVDA")
    adapter = client.LiveTradingAgentsAdapter(config)
    with pytest.raises(TradingAgentsUnavailableError, match="not installed"):
        adapter.run(build_research_request(FIXED_START), snapshot, now=FIXED_START)


def _raise_import_error() -> type:
    raise ImportError("No module named 'tradingagents'")


def test_version_mismatch_fails_before_any_upstream_call(
    config: AdapterConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    FakeGraph.reset()
    monkeypatch.setattr(client, "_load_graph_class", lambda: FakeGraph)
    monkeypatch.setattr(client, "_installed_version", lambda: "9.9.9")
    snapshot = make_market_snapshot(FIXED_START, instrument_id="NVDA")
    adapter = client.LiveTradingAgentsAdapter(config)
    with pytest.raises(TradingAgentsVersionError, match="violates the pin"):
        adapter.run(build_research_request(FIXED_START), snapshot, now=FIXED_START)
    assert FakeGraph.instances == []


def test_upstream_crash_retries_then_succeeds(
    config: AdapterConfig, fake_upstream: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    FakeGraph.next_queues = [[RuntimeError("boom")], [RuntimeError("boom")]]
    sleeps: list[float] = []
    snapshot = make_market_snapshot(FIXED_START, instrument_id="NVDA")
    adapter = client.LiveTradingAgentsAdapter(
        config.model_copy(update={"retry_max_attempts": 3, "retry_base_delay_seconds": 0.01}),
        sleep=lambda s: sleeps.append(s),
    )
    signal = adapter.run(build_research_request(FIXED_START), snapshot, now=FIXED_START)
    assert signal.direction is SignalDirection.LONG
    assert len(FakeGraph.instances) == 3
    assert len(sleeps) == 2


def test_upstream_crash_budget_exhausted_fails_safely(
    config: AdapterConfig, fake_upstream: None
) -> None:
    FakeGraph.next_queues = [[RuntimeError("boom")], [RuntimeError("boom")]]
    snapshot = make_market_snapshot(FIXED_START, instrument_id="NVDA")
    adapter = client.LiveTradingAgentsAdapter(config)
    with pytest.raises(TradingAgentsError, match="propagate failed"):
        adapter.run(build_research_request(FIXED_START), snapshot, now=FIXED_START)
    assert len(FakeGraph.instances) == 2


def test_timeout_budget_raises_and_is_retried(config: AdapterConfig, fake_upstream: None) -> None:
    FakeGraph.sleep_seconds = 0.2
    quick = config.model_copy(update={"timeout_seconds": 0.02})
    snapshot = make_market_snapshot(FIXED_START, instrument_id="NVDA")
    adapter = client.LiveTradingAgentsAdapter(quick)
    with pytest.raises(TradingAgentsTimeoutError, match="timeout"):
        adapter.run(build_research_request(FIXED_START), snapshot, now=FIXED_START)
    assert len(FakeGraph.instances) == quick.retry_max_attempts


def test_mapping_error_never_touches_upstream(
    config: AdapterConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    FakeGraph.reset()
    monkeypatch.setattr(client, "_load_graph_class", lambda: FakeGraph)
    monkeypatch.setattr(client, "_installed_version", lambda: "0.3.1")
    request = build_research_request(FIXED_START)  # no instrument/as_of context
    adapter = client.LiveTradingAgentsAdapter(config)
    with pytest.raises(TradingAgentsMappingError):
        adapter.run(request, None, now=FIXED_START)
    assert FakeGraph.instances == []


def test_rating_crosscheck_conflict_fails_safely(
    config: AdapterConfig, fake_upstream: None
) -> None:
    state = fake_state()
    state["final_trade_decision"] = "**Rating**: Sell\n\n**Executive Summary**: exit."
    FakeGraph.next_queues = [[(state, "Buy")]]
    snapshot = make_market_snapshot(FIXED_START, instrument_id="NVDA")
    adapter = client.LiveTradingAgentsAdapter(config)
    with pytest.raises(TradingAgentsMappingError, match="disagrees"):
        adapter.run(build_research_request(FIXED_START), snapshot, now=FIXED_START)


def test_graph_construction_failure_fails_safely(
    config: AdapterConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    class BrokenGraph:
        def __init__(self, **kwargs: object) -> None:
            raise RuntimeError("provider unavailable")

    monkeypatch.setattr(client, "_load_graph_class", lambda: BrokenGraph)
    monkeypatch.setattr(client, "_installed_version", lambda: "0.3.1")
    snapshot = make_market_snapshot(FIXED_START, instrument_id="NVDA")
    adapter = client.LiveTradingAgentsAdapter(config)
    with pytest.raises(TradingAgentsUnavailableError, match="instantiate"):
        adapter.run(build_research_request(FIXED_START), snapshot, now=FIXED_START)


# ── TokenUsageCollector ───────────────────────────────────────────────────────


def test_collector_accumulates_legacy_usage() -> None:
    collector = client.TokenUsageCollector()
    collector.on_llm_end(
        FakeResponse(usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150})
    )
    collector.on_llm_end(FakeResponse(usage={"prompt_tokens": 20, "completion_tokens": 10}))
    usage = collector.to_token_usage()
    assert usage is not None
    assert usage.calls == 2
    assert usage.prompt_tokens == 120
    assert usage.completion_tokens == 60
    assert usage.total_tokens == 150  # explicit totals are not double-counted


def test_collector_reads_usage_metadata() -> None:
    collector = client.TokenUsageCollector()
    collector.on_llm_end(FakeResponse(usage_metadata={"input_tokens": 10, "output_tokens": 5}))
    usage = collector.to_token_usage()
    assert usage is not None
    assert usage.prompt_tokens == 10
    assert usage.completion_tokens == 5
    assert usage.total_tokens == 15


def test_collector_returns_none_without_calls() -> None:
    assert client.TokenUsageCollector().to_token_usage() is None
