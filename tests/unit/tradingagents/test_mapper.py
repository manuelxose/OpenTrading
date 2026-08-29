"""Unit tests: ResearchRequest/MarketSnapshot ↔ TradingAgents ↔ LLMSignal mapping."""

from __future__ import annotations

from datetime import timedelta

import pytest
from adapters.tradingagents import mapper
from adapters.tradingagents.errors import TradingAgentsMappingError
from adapters.tradingagents.schemas import (
    ModelMetadata,
    TokenUsage,
    TradingAgentsRating,
    UpstreamRunResult,
)
from core.domain.enums import SignalDirection
from core.schemas.signals import LLMSignal
from ta_test_helpers import build_research_request, fake_state

from factories import FIXED_START, make_market_snapshot


def make_result(
    decision: str = "**Rating**: Buy", rating: TradingAgentsRating | None = None
) -> UpstreamRunResult:
    return UpstreamRunResult(
        ticker="NVDA",
        trade_date="2024-05-10",
        as_of=FIXED_START,
        rating=rating or TradingAgentsRating.BUY,
        decision_markdown=decision,
        model_metadata=ModelMetadata(
            provider="fake",
            deep_think_llm="deep-x",
            quick_think_llm="quick-x",
            upstream_version="0.3.1",
            prompt_version="v1",
        ),
        latency_ms=42,
    )


# ── 5-tier profile ────────────────────────────────────────────────────────────


def test_rating_profile_covers_all_tiers() -> None:
    assert set(mapper.RATING_PROFILE) == set(TradingAgentsRating)
    assert mapper.RATING_PROFILE[TradingAgentsRating.BUY] == (SignalDirection.LONG, 0.90, 0.80)
    assert mapper.RATING_PROFILE[TradingAgentsRating.OVERWEIGHT] == (
        SignalDirection.LONG,
        0.70,
        0.70,
    )
    assert mapper.RATING_PROFILE[TradingAgentsRating.HOLD] == (SignalDirection.FLAT, 0.50, 0.50)
    assert mapper.RATING_PROFILE[TradingAgentsRating.UNDERWEIGHT] == (
        SignalDirection.SHORT,
        0.70,
        0.70,
    )
    assert mapper.RATING_PROFILE[TradingAgentsRating.SELL] == (SignalDirection.SHORT, 0.90, 0.80)


@pytest.mark.parametrize(
    ("rating", "expected"),
    [
        (TradingAgentsRating.BUY, SignalDirection.LONG),
        (TradingAgentsRating.OVERWEIGHT, SignalDirection.LONG),
        (TradingAgentsRating.HOLD, SignalDirection.FLAT),
        (TradingAgentsRating.UNDERWEIGHT, SignalDirection.SHORT),
        (TradingAgentsRating.SELL, SignalDirection.SHORT),
    ],
)
def test_result_to_signal_maps_direction(
    rating: TradingAgentsRating, expected: SignalDirection
) -> None:
    request = build_research_request(FIXED_START)
    result = make_result(f"**Rating**: {rating.value}", rating=rating)
    signal = mapper.result_to_signal(result, request=request, produced_at=FIXED_START)
    assert signal.direction is expected


# ── rating parsing ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("**Rating**: Buy\n\n**Executive Summary**: ...", TradingAgentsRating.BUY),
        ("Rating: Underweight\nmore text", TradingAgentsRating.UNDERWEIGHT),
        ("Overweight", TradingAgentsRating.OVERWEIGHT),
        ("**Rating**: Sell", TradingAgentsRating.SELL),
    ],
)
def test_parse_rating_variants(text: str, expected: TradingAgentsRating) -> None:
    assert mapper.parse_rating(text) is expected


def test_parse_rating_unknown_tier_fails_safely() -> None:
    with pytest.raises(TradingAgentsMappingError):
        mapper.parse_rating("**Rating**: Strong Buy")


# ── request → upstream input ──────────────────────────────────────────────────


def test_request_to_upstream_input_uses_snapshot_as_of_and_ticker() -> None:
    t = FIXED_START
    snapshot = make_market_snapshot(t, instrument_id="NVDA")
    request = build_research_request(t, instrument="NVDA")
    upstream = mapper.request_to_upstream_input(request, snapshot)
    assert upstream.ticker == "NVDA"
    assert upstream.trade_date == "2026-01-05"
    assert upstream.asset_type == "stock"
    assert upstream.as_of == t
    assert upstream.context_payload["instrument_id"] == "NVDA"
    assert "NVDA" in upstream.context_payload["rendered"]


def test_explicit_as_of_required_without_snapshot() -> None:
    request = build_research_request(FIXED_START)  # no as_of in context
    with pytest.raises(TradingAgentsMappingError, match="explicit as_of"):
        mapper.request_to_upstream_input(request, None)


def test_context_as_of_supported_without_snapshot() -> None:
    request = build_research_request(FIXED_START, as_of="2026-01-05T10:00:00+00:00")
    upstream = mapper.request_to_upstream_input(request, None)
    assert upstream.trade_date == "2026-01-05"
    assert upstream.as_of == FIXED_START


def test_conflicting_as_of_rejected() -> None:
    snapshot = make_market_snapshot(FIXED_START, instrument_id="NVDA")
    request = build_research_request(FIXED_START, as_of="2026-01-06T10:00:00+00:00")
    with pytest.raises(TradingAgentsMappingError, match="conflicts"):
        mapper.request_to_upstream_input(request, snapshot)


def test_conflicting_instrument_rejected() -> None:
    snapshot = make_market_snapshot(FIXED_START, instrument_id="NVDA")
    request = build_research_request(FIXED_START, instrument="TSLA")
    with pytest.raises(TradingAgentsMappingError, match="conflicts"):
        mapper.request_to_upstream_input(request, snapshot)


def test_missing_instrument_rejected() -> None:
    request = build_research_request(FIXED_START, as_of=FIXED_START.isoformat())
    request = request.model_copy(update={"context": {"as_of": FIXED_START.isoformat()}})
    with pytest.raises(TradingAgentsMappingError, match="instrument"):
        mapper.request_to_upstream_input(request, None)


def test_point_in_time_evidence_after_as_of_rejected() -> None:
    snapshot = make_market_snapshot(FIXED_START, instrument_id="NVDA")
    request = build_research_request(
        FIXED_START,
        evidence=[{"ref_id": "x", "valid_at": (FIXED_START + timedelta(days=1)).isoformat()}],
    )
    with pytest.raises(TradingAgentsMappingError, match="posterior"):
        mapper.request_to_upstream_input(request, snapshot)


def test_point_in_time_evidence_valid_at_accepted() -> None:
    snapshot = make_market_snapshot(FIXED_START, instrument_id="NVDA")
    request = build_research_request(
        FIXED_START,
        evidence=[{"ref_id": "x", "valid_at": FIXED_START.isoformat()}],
    )
    upstream = mapper.request_to_upstream_input(request, snapshot)
    assert upstream.ticker == "NVDA"


def test_evidence_without_valid_at_rejected() -> None:
    snapshot = make_market_snapshot(FIXED_START, instrument_id="NVDA")
    request = build_research_request(FIXED_START, evidence=[{"ref_id": "x"}])
    with pytest.raises(TradingAgentsMappingError, match="valid_at"):
        mapper.request_to_upstream_input(request, snapshot)


def test_asset_type_must_be_stock_or_crypto() -> None:
    snapshot = make_market_snapshot(FIXED_START, instrument_id="NVDA")
    request = build_research_request(FIXED_START, asset_type="forex")
    with pytest.raises(TradingAgentsMappingError, match="asset_type"):
        mapper.request_to_upstream_input(request, snapshot)


# ── state → result / evidence preservation ────────────────────────────────────


def test_state_to_result_preserves_committee_evidence() -> None:
    state = fake_state()
    result = mapper.state_to_result(
        state,
        ticker="NVDA",
        as_of=FIXED_START,
        rating=TradingAgentsRating.BUY,
        latency_ms=7,
        model_metadata=make_result().model_metadata,
        token_usage=None,
        cost_usd=None,
    )
    assert result.decision_markdown.startswith("**Rating**: Buy")
    assert result.investment_plan.startswith("**Recommendation**: Buy")
    assert result.trader_plan.endswith("FINAL TRANSACTION PROPOSAL: **BUY**")
    assert result.analyst_reports["fundamentals_report"] == state["fundamentals_report"]
    assert result.analyst_reports["market_report"] == state["market_report"]
    assert result.analyst_reports["sentiment_report"] == state["sentiment_report"]
    assert result.analyst_reports["news_report"] == state["news_report"]
    assert result.bull_history == state["investment_debate_state"]["bull_history"]
    assert result.bear_history == state["investment_debate_state"]["bear_history"]
    assert result.risk_history == state["risk_debate_state"]["history"]


def test_result_to_signal_preserves_roles_in_order() -> None:
    request = build_research_request(FIXED_START)
    result = mapper.state_to_result(
        fake_state(),
        ticker="NVDA",
        as_of=FIXED_START,
        rating=TradingAgentsRating.BUY,
        latency_ms=7,
        model_metadata=make_result().model_metadata,
        token_usage=TokenUsage(calls=3, prompt_tokens=9, completion_tokens=4, total_tokens=13),
        cost_usd=0.01,
    )
    signal = mapper.result_to_signal(result, request=request, produced_at=FIXED_START)
    roles = [(member.name, member.role) for member in signal.committee]
    assert roles == [
        ("Fundamentals Analyst", "analyst"),
        ("Market Analyst", "analyst"),
        ("Sentiment Analyst", "analyst"),
        ("News Analyst", "analyst"),
        ("Bull Researcher", "researcher"),
        ("Bear Researcher", "researcher"),
        ("Trader", "trader"),
        ("Portfolio Manager", "portfolio_manager"),
    ]
    by_name = {member.name: member for member in signal.committee}
    assert by_name["Bull Researcher"].stance is SignalDirection.LONG
    assert by_name["Bear Researcher"].stance is SignalDirection.SHORT
    assert by_name["Trader"].stance is SignalDirection.LONG  # parsed BUY action
    assert by_name["Portfolio Manager"].stance is SignalDirection.LONG
    # analyst evidence text preserved verbatim
    assert by_name["Market Analyst"].argument == fake_state()["market_report"]


def test_result_to_signal_captures_metadata_trace_and_usage() -> None:
    request = build_research_request(FIXED_START)
    result = make_result()
    signal = mapper.result_to_signal(
        result, request=request, trace_id=request.request_id, produced_at=FIXED_START
    )
    assert signal.model_name == "deep-x"
    assert signal.provider == "fake"
    assert signal.prompt_version == "v1"
    assert signal.trace_id == request.request_id
    assert signal.as_of == FIXED_START
    assert signal.latency_ms == 42
    assert signal.provenance.producer == "adapters.tradingagents"
    assert signal.provenance.source_ids["request_id"] == str(request.request_id)
    assert signal.provenance.source_ids["upstream_version"] == "0.3.1"


def test_signal_id_is_deterministic_for_same_inputs() -> None:
    request = build_research_request(FIXED_START)
    one = mapper.result_to_signal(make_result(), request=request, produced_at=FIXED_START)
    two = mapper.result_to_signal(make_result(), request=request, produced_at=FIXED_START)
    assert one.signal_id == two.signal_id
    other = mapper.result_to_signal(
        make_result(),
        request=request,
        trace_id=request.request_id,
        produced_at=FIXED_START + timedelta(days=1),
    )
    assert other.signal_id == one.signal_id  # signal id is as_of-based, not produced_at-based


def test_signal_is_canonical_llm_signal() -> None:
    request = build_research_request(FIXED_START)
    signal = mapper.result_to_signal(make_result(), request=request, produced_at=FIXED_START)
    assert isinstance(signal, LLMSignal)
    assert signal.schema_version == LLMSignal.SCHEMA_VERSION
    assert signal.evidence_refs


# ── stances ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Strong growth, bullish momentum, upside surprise.", SignalDirection.LONG),
        ("Weak demand, bearish momentum, downside risk.", SignalDirection.SHORT),
        ("The data is balanced overall.", SignalDirection.FLAT),
    ],
)
def test_infer_stance(text: str, expected: SignalDirection) -> None:
    assert mapper.infer_stance(text, default=SignalDirection.FLAT) is expected


def test_parse_trader_action_variants() -> None:
    assert mapper.parse_trader_action("FINAL TRANSACTION PROPOSAL: **BUY**") is SignalDirection.LONG
    assert mapper.parse_trader_action("FINAL TRANSACTION PROPOSAL: SELL") is SignalDirection.SHORT
    assert mapper.parse_trader_action("**Action**: Hold") is SignalDirection.FLAT
    assert mapper.parse_trader_action("no proposal here") is None


# ── no execution capability ───────────────────────────────────────────────────


def test_signal_never_carries_execution_fields() -> None:
    execution_vocabulary = ("order", "intent", "quantity", "sizing", "stop", "lot")
    for field in LLMSignal.model_fields:
        assert field not in execution_vocabulary
    request = build_research_request(FIXED_START)
    signal = mapper.result_to_signal(make_result(), request=request, produced_at=FIXED_START)
    for member in signal.committee:
        assert "size" not in type(member).model_fields
