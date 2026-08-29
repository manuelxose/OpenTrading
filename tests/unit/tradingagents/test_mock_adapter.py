"""Unit tests: deterministic mock TradingAgents adapter."""

from __future__ import annotations

from datetime import timedelta

import pytest
from adapters.tradingagents import MockTradingAgentsAdapter, default_mock_scenario
from adapters.tradingagents.errors import TradingAgentsError
from adapters.tradingagents.schemas import MockScenario, TradingAgentsRating
from core.domain.enums import SignalDirection
from ta_test_helpers import build_research_request

from factories import FIXED_START, make_market_snapshot


def make_buy_scenario() -> MockScenario:
    return MockScenario(
        scenario_id="nvda-buy",
        rating=TradingAgentsRating.BUY,
        decision_markdown="**Rating**: Buy\n\n**Executive Summary**: build.\n\n"
        "**Investment Thesis**: growth persists.",
        investment_plan="**Recommendation**: Buy",
        trader_plan="FINAL TRANSACTION PROPOSAL: **BUY**",
        analyst_reports={
            "fundamentals_report": "growth is accelerating",
            "market_report": "uptrend intact",
            "sentiment_report": "bullish",
            "news_report": "positive catalysts",
        },
        bull_history="bull case",
        bear_history="bear case",
    )


def test_default_scenario_is_hold() -> None:
    adapter = MockTradingAgentsAdapter()
    request = build_research_request(FIXED_START)
    signal = adapter.run(
        request, make_market_snapshot(FIXED_START, instrument_id="NVDA"), now=FIXED_START
    )
    assert signal.direction is SignalDirection.FLAT
    assert signal.strength == 0.5
    assert signal.reasoning.startswith("**Rating**: Hold")
    assert signal.model_name == "mock-deep-model"
    assert signal.provider == "mock-provider"


def test_scenario_selected_by_ticker() -> None:
    adapter = MockTradingAgentsAdapter(scenarios={"NVDA": make_buy_scenario()})
    request = build_research_request(FIXED_START)
    signal = adapter.run(
        request, make_market_snapshot(FIXED_START, instrument_id="NVDA"), now=FIXED_START
    )
    assert signal.direction is SignalDirection.LONG
    assert signal.strength == 0.90


def test_scenario_selected_by_ticker_and_date() -> None:
    adapter = MockTradingAgentsAdapter(
        scenarios={"NVDA@2026-01-05": make_buy_scenario()},
        default=default_mock_scenario(),
    )
    request = build_research_request(FIXED_START)
    signal = adapter.run(
        request, make_market_snapshot(FIXED_START, instrument_id="NVDA"), now=FIXED_START
    )
    assert signal.direction is SignalDirection.LONG
    # A different trade date falls back to the default HOLD.
    other = FIXED_START + timedelta(days=7)
    signal = adapter.run(
        build_research_request(other),
        make_market_snapshot(other, instrument_id="NVDA"),
        now=other,
    )
    assert signal.direction is SignalDirection.FLAT


def test_failure_injection_fails_safely() -> None:
    adapter = MockTradingAgentsAdapter(fail_for={"NVDA"})
    request = build_research_request(FIXED_START)
    with pytest.raises(TradingAgentsError, match="mock failure injected"):
        adapter.run(
            request,
            make_market_snapshot(FIXED_START, instrument_id="NVDA"),
            now=FIXED_START,
        )


def test_deterministic_replay() -> None:
    adapter = MockTradingAgentsAdapter(scenarios={"NVDA": make_buy_scenario()})
    snapshot = make_market_snapshot(FIXED_START, instrument_id="NVDA")
    request = build_research_request(FIXED_START)
    one = adapter.run(request, snapshot, now=FIXED_START)
    two = adapter.run(request, snapshot, now=FIXED_START)
    assert one.signal_id == two.signal_id
    assert one.model_dump_json() == two.model_dump_json()


def test_mock_shares_mapping_validation_with_live() -> None:
    adapter = MockTradingAgentsAdapter()
    request = build_research_request(FIXED_START)  # no instrument/as_of context
    with pytest.raises(TradingAgentsError):
        adapter.run(request, None, now=FIXED_START)


def test_mock_preserves_committee_evidence() -> None:
    adapter = MockTradingAgentsAdapter(scenarios={"NVDA": make_buy_scenario()})
    request = build_research_request(FIXED_START)
    signal = adapter.run(
        request, make_market_snapshot(FIXED_START, instrument_id="NVDA"), now=FIXED_START
    )
    roles = {member.role for member in signal.committee}
    assert roles == {"analyst", "researcher", "trader", "portfolio_manager"}
    assert signal.cost_usd == 0.001
    assert signal.latency_ms == 25
