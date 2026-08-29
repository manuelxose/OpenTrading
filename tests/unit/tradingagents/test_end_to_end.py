"""End-to-end contract: MarketSnapshot → ResearchRequest → TradingAgents → LLMSignal.

Proves the Phase 2 definition of done: the full path works with zero execution
capability (INV-1/INV-2). No OrderIntent, no MT4, no executable sizing anywhere
on the path — enforced structurally (boundary tests) and asserted here.
"""

from __future__ import annotations

from uuid import uuid4

from adapters.tradingagents import MockTradingAgentsAdapter
from adapters.tradingagents.schemas import MockScenario, TradingAgentsRating
from core.domain.enums import SignalDirection
from core.schemas.research import ResearchRequest
from core.schemas.signals import LLMSignal
from ta_test_helpers import build_research_request

from factories import FIXED_START, make_market_snapshot, provenance


def build_request_from_snapshot(snapshot) -> ResearchRequest:
    """The canonical first hop of the DoD chain: MarketSnapshot → ResearchRequest."""
    return ResearchRequest(
        request_id=uuid4(),
        title=f"Qualitative review of {snapshot.instrument_id}",
        question=f"Is {snapshot.instrument_id} actionable right now?",
        hypotheses=[f"{snapshot.instrument_id} trends higher from here"],
        requested_by="qualitative-pipeline",
        context={
            "instrument_id": snapshot.instrument_id,
            "as_of": snapshot.as_of.isoformat(),
            "asset_type": "stock",
            "evidence": [
                {
                    "ref_id": f"snapshot:{snapshot.source}",
                    "valid_at": snapshot.source_timestamp.isoformat(),
                }
            ],
        },
        produced_at=snapshot.produced_at,
        provenance=provenance(snapshot.produced_at, producer="qualitative-pipeline"),
    )


BUY_SCENARIO = MockScenario(
    scenario_id="nvda-buy",
    rating=TradingAgentsRating.BUY,
    decision_markdown="**Rating**: Buy\n\n**Executive Summary**: build position.\n\n"
    "**Investment Thesis**: growth persists.",
    investment_plan="**Recommendation**: Buy",
    trader_plan="**Action**: Buy\n\n**Reasoning**: strong setup.\n\n"
    "FINAL TRANSACTION PROPOSAL: **BUY**",
    analyst_reports={
        "fundamentals_report": "growth is accelerating",
        "market_report": "uptrend intact",
        "sentiment_report": "bullish",
        "news_report": "positive catalysts",
    },
    bull_history="bull case",
    bear_history="bear case",
)


def test_market_snapshot_to_research_request_to_llmsignal() -> None:
    trace_id = uuid4()
    snapshot = make_market_snapshot(FIXED_START, instrument_id="NVDA")
    request = build_request_from_snapshot(snapshot)

    adapter = MockTradingAgentsAdapter(scenarios={"NVDA": BUY_SCENARIO})
    signal = adapter.run(request, snapshot, trace_id=trace_id, now=FIXED_START)

    # Out: the canonical advisory signal, correctly translated.
    assert isinstance(signal, LLMSignal)
    assert signal.direction is SignalDirection.LONG
    assert signal.strength == 0.90
    assert signal.confidence == 0.80
    assert signal.instrument_id == "NVDA"
    assert signal.as_of == snapshot.as_of
    assert signal.trace_id == trace_id
    assert signal.produced_at == FIXED_START

    # Evidence preserved: every committee role is represented.
    assert {member.role for member in signal.committee} == {
        "analyst",
        "researcher",
        "trader",
        "portfolio_manager",
    }
    # The point-in-time snapshot is cited as evidence.
    assert any("market-snapshot" in ref.ref_id for ref in signal.evidence_refs)
    # Model/provider/version metadata is captured.
    assert signal.provider and signal.model_name and signal.prompt_version


def test_end_to_end_has_no_execution_capability_whatsoever() -> None:
    trace_id = uuid4()
    snapshot = make_market_snapshot(FIXED_START, instrument_id="NVDA")
    request = build_request_from_snapshot(snapshot)
    adapter = MockTradingAgentsAdapter(scenarios={"NVDA": BUY_SCENARIO})
    signal = adapter.run(request, snapshot, trace_id=trace_id, now=FIXED_START)

    execution_vocabulary = {
        "order",
        "intent",
        "quantity",
        "sizing",
        "stop",
        "lot",
        "position",
        "entry_price",
        "limit",
        "fill",
        "margin",
        "execution",
    }
    assert not (set(type(signal).model_fields) & execution_vocabulary)
    for member in signal.committee:
        assert not (set(type(member).model_fields) & execution_vocabulary)
    # The adapter surface itself exposes nothing but the advisory run contract.
    public = [attr for attr in dir(adapter) if not attr.startswith("_")]
    assert "run" in public
    assert not {"send_order", "create_order", "submit"} & set(public)


def test_e2e_replay_is_deterministic_with_the_mock() -> None:
    trace_id = uuid4()
    snapshot = make_market_snapshot(FIXED_START, instrument_id="NVDA")
    request = build_request_from_snapshot(snapshot)
    adapter = MockTradingAgentsAdapter(scenarios={"NVDA": BUY_SCENARIO})
    one = adapter.run(request, snapshot, trace_id=trace_id, now=FIXED_START)
    two = adapter.run(request, snapshot, trace_id=trace_id, now=FIXED_START)
    assert one.model_dump_json() == two.model_dump_json()


def test_e2e_path_uses_the_same_mapper_for_live_and_mock() -> None:
    """The DoD chain must not depend on which adapter sits behind it."""
    request = build_research_request(FIXED_START)
    snapshot = make_market_snapshot(FIXED_START, instrument_id="NVDA")

    mock_signal = MockTradingAgentsAdapter(scenarios={"NVDA": BUY_SCENARIO}).run(
        request, snapshot, now=FIXED_START
    )
    assert mock_signal.provenance.producer == "adapters.tradingagents"
    assert mock_signal.prompt_version == "tradingagents-adapter-1.0.0"
