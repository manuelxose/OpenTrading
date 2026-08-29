"""Evaluation harness tests over the historical scenario fixtures."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from adapters.tradingagents import MockTradingAgentsAdapter
from adapters.tradingagents import evaluator as ev
from adapters.tradingagents.schemas import TradingAgentsRating
from core.domain.enums import SignalDirection

from factories import FIXED_START


def test_scenario_fixtures_load_and_cover_all_tiers() -> None:
    scenarios = ev.load_scenarios()
    assert len(scenarios) >= 5, "need several historical scenarios"
    ratings = {scenario.expected_rating for scenario in scenarios}
    assert ratings == set(TradingAgentsRating), f"fixtures must cover all 5 tiers: {ratings}"

    for fixture in scenarios:
        assert fixture.source_timestamp <= fixture.as_of, (
            f"{fixture.scenario_id}: source_timestamp must not be posterior to as_of"
        )
        assert Decimal(fixture.bid) <= Decimal(fixture.ask)


def test_fixture_to_request_and_snapshot_are_valid_contracts() -> None:
    for fixture in ev.load_scenarios():
        request = ev.fixture_to_request(fixture, produced_at=FIXED_START)
        snapshot = ev.fixture_to_snapshot(fixture, produced_at=FIXED_START)
        assert request.question == fixture.question
        assert snapshot.instrument_id == fixture.instrument_id
        assert snapshot.as_of == fixture.as_of
        assert snapshot.source_timestamp <= snapshot.as_of


def test_evaluate_all_scenarios_pass_with_mock_adapter() -> None:
    scenarios = ev.load_scenarios()
    trace_id = uuid4()
    producer = MockTradingAgentsAdapter(
        scenarios={
            fixture.instrument_id: ev.fixture_to_mock_scenario(fixture) for fixture in scenarios
        }
    )
    reports = ev.evaluate_all(producer, scenarios, trace_id=trace_id, produced_at=FIXED_START)
    assert len(reports) == len(scenarios)
    for report in reports:
        assert report.passed, f"{report.scenario_id}: {report.failures}"
        assert report.execution_capability == "none"
        assert report.trace_id_propagated
        assert report.as_of_correct
        assert report.metadata_captured
        assert report.token_usage_captured
        assert report.evidence_preserved == {
            "analysts": True,
            "researchers": True,
            "trader": True,
            "portfolio_manager": True,
        }


def test_evaluate_reports_expected_direction_per_tier() -> None:
    expected = {
        TradingAgentsRating.BUY: SignalDirection.LONG,
        TradingAgentsRating.OVERWEIGHT: SignalDirection.LONG,
        TradingAgentsRating.HOLD: SignalDirection.FLAT,
        TradingAgentsRating.UNDERWEIGHT: SignalDirection.SHORT,
        TradingAgentsRating.SELL: SignalDirection.SHORT,
    }
    scenarios = {s.scenario_id: s for s in ev.load_scenarios()}
    producer = MockTradingAgentsAdapter(
        scenarios={
            fixture.instrument_id: ev.fixture_to_mock_scenario(fixture)
            for fixture in scenarios.values()
        }
    )
    trace_id = uuid4()
    for fixture in scenarios.values():
        signal = producer.run(
            ev.fixture_to_request(fixture, produced_at=FIXED_START, trace_id=trace_id),
            ev.fixture_to_snapshot(fixture, produced_at=FIXED_START),
            trace_id=trace_id,
            now=FIXED_START,
        )
        assert signal.direction is expected[fixture.expected_rating], fixture.scenario_id
