"""Evaluation harness for historical TradingAgents scenarios.

Fixtures live in ``data/eval/tradingagents/scenarios/*.json``. Each fixture is a
historical scenario: a point-in-time ``MarketSnapshot`` + a ``ResearchRequest``
+ the mock committee output the scenario should produce + the expected
canonical rating. The evaluator checks, per requirement:

- direction/strength/confidence match the documented 5-tier profile;
- analyst / researcher / trader / portfolio-manager evidence is preserved;
- model/provider/version metadata is captured;
- token usage is captured when available (proxied by cost/latency presence);
- ``trace_id`` is propagated;
- ``as_of`` is respected;
- the signal carries no execution capability whatsoever (INV-1/INV-2).

Used by ``tests/unit/tradingagents/test_evaluator.py`` and usable later against
the live adapter for provider/seed comparisons (§21).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

from core.schemas.base import Provenance
from core.schemas.market import MarketSnapshot
from core.schemas.research import ResearchRequest
from core.schemas.signals import LLMSignal
from pydantic import BaseModel, ConfigDict, Field

from adapters.tradingagents import mapper
from adapters.tradingagents.schemas import MockScenario, TradingAgentsRating

__all__ = [
    "DEFAULT_SCENARIOS_DIR",
    "EvalReport",
    "ScenarioFixture",
    "evaluate",
    "evaluate_all",
    "fixture_to_mock_scenario",
    "fixture_to_request",
    "fixture_to_snapshot",
    "load_scenarios",
]

DEFAULT_SCENARIOS_DIR = (
    Path(__file__).resolve().parents[2] / "data" / "eval" / "tradingagents" / "scenarios"
)

#: Execution-capability vocabulary that must never appear in the signal schema.
_EXECUTION_VOCABULARY = (
    "order",
    "intent",
    "quantity",
    "sizing",
    "stop",
    "lot",
    "entry_price",
    "position_size",
)


class ScenarioFixture(BaseModel):
    """One historical evaluation scenario (JSON-serializable)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    instrument_id: str = Field(min_length=1)
    asset_type: str = Field(default="stock")
    as_of: datetime
    source_timestamp: datetime
    bid: str
    ask: str
    source: str = Field(default="eval-fixture")
    question: str = Field(min_length=1)
    hypotheses: list[str] = Field(default_factory=list)
    expected_rating: TradingAgentsRating
    mock_decision: MockScenario


class EvalReport(BaseModel):
    """Result of evaluating one scenario signal against the requirements."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    passed: bool
    direction_correct: bool
    strength_correct: bool
    confidence_correct: bool
    evidence_preserved: dict[str, bool] = Field(default_factory=dict)
    metadata_captured: bool
    token_usage_captured: bool
    trace_id_propagated: bool
    as_of_correct: bool
    execution_capability: str = "none"
    failures: list[str] = Field(default_factory=list)


class SignalProducer(Protocol):
    """Minimal surface the evaluator needs from any adapter."""

    def run(
        self,
        request: ResearchRequest,
        snapshot: MarketSnapshot | None = None,
        *,
        trace_id: UUID | None = None,
        now: datetime | None = None,
    ) -> LLMSignal: ...


def load_scenarios(directory: Path | None = None) -> list[ScenarioFixture]:
    """Load every ``*.json`` scenario under ``directory`` (sorted by name)."""
    path = directory or DEFAULT_SCENARIOS_DIR
    scenarios = [
        ScenarioFixture.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(path.glob("*.json"))
    ]
    if not scenarios:
        raise FileNotFoundError(f"no scenario fixtures found under {path}")
    return scenarios


def fixture_to_request(
    fixture: ScenarioFixture, *, produced_at: datetime, trace_id: UUID | None = None
) -> ResearchRequest:
    """Build the canonical request for a fixture (deterministic request_id)."""
    request_id = uuid5(NAMESPACE_URL, f"eval:{fixture.scenario_id}")
    return ResearchRequest(
        request_id=request_id,
        title=f"Evaluation scenario {fixture.scenario_id}",
        question=fixture.question,
        hypotheses=list(fixture.hypotheses),
        requested_by="tradingagents-evaluator",
        context={
            "instrument_id": fixture.instrument_id,
            "asset_type": fixture.asset_type,
            "as_of": fixture.as_of.isoformat(),
            "eval_scenario": fixture.scenario_id,
        },
        trace_id=trace_id,
        produced_at=produced_at,
        provenance=Provenance(producer="adapters.tradingagents.evaluator", produced_at=produced_at),
    )


def fixture_to_snapshot(fixture: ScenarioFixture, *, produced_at: datetime) -> MarketSnapshot:
    """Build the point-in-time snapshot for a fixture (INV-3: valid at as_of)."""
    return MarketSnapshot(
        instrument_id=fixture.instrument_id,
        as_of=fixture.as_of,
        source_timestamp=fixture.source_timestamp,
        bid=Decimal(fixture.bid),
        ask=Decimal(fixture.ask),
        source=fixture.source,
        produced_at=produced_at,
        provenance=Provenance(producer="adapters.tradingagents.evaluator", produced_at=produced_at),
    )


def fixture_to_mock_scenario(fixture: ScenarioFixture) -> MockScenario:
    """The mock committee output a scenario expects to be played back."""
    return fixture.mock_decision


def evaluate(signal: LLMSignal, fixture: ScenarioFixture, *, trace_id: UUID) -> EvalReport:
    """Score one signal against the scenario and the adapter requirements."""
    expected_direction, expected_strength, expected_confidence = mapper.RATING_PROFILE[
        fixture.expected_rating
    ]

    roles = {member.role for member in signal.committee}
    evidence_preserved = {
        "analysts": "analyst" in roles,
        "researchers": "researcher" in roles,
        "trader": "trader" in roles,
        "portfolio_manager": "portfolio_manager" in roles,
    }
    metadata_captured = bool(signal.provider and signal.model_name and signal.prompt_version)
    token_usage_captured = signal.cost_usd is not None and signal.latency_ms is not None
    trace_id_propagated = signal.trace_id == trace_id
    as_of_correct = signal.as_of == fixture.as_of

    execution_capability = "none"
    for field in type(signal).model_fields:
        if field in _EXECUTION_VOCABULARY:
            execution_capability = f"execution field present: {field}"

    checks = {
        "direction_correct": signal.direction == expected_direction,
        "strength_correct": signal.strength == expected_strength,
        "confidence_correct": signal.confidence == expected_confidence,
        "evidence_preserved": all(evidence_preserved.values()),
        "metadata_captured": metadata_captured,
        "token_usage_captured": token_usage_captured,
        "trace_id_propagated": trace_id_propagated,
        "as_of_correct": as_of_correct,
        "execution_capability": execution_capability == "none",
    }
    failures = [name for name, ok in checks.items() if not ok]
    return EvalReport(
        scenario_id=fixture.scenario_id,
        passed=not failures,
        direction_correct=checks["direction_correct"],
        strength_correct=checks["strength_correct"],
        confidence_correct=checks["confidence_correct"],
        evidence_preserved=evidence_preserved,
        metadata_captured=metadata_captured,
        token_usage_captured=token_usage_captured,
        trace_id_propagated=trace_id_propagated,
        as_of_correct=as_of_correct,
        execution_capability=execution_capability,
        failures=failures,
    )


def evaluate_all(
    producer: SignalProducer,
    scenarios: list[ScenarioFixture],
    *,
    trace_id: UUID,
    produced_at: datetime,
) -> list[EvalReport]:
    """Run every scenario through ``producer`` and score the resulting signals."""
    reports: list[EvalReport] = []
    for fixture in scenarios:
        signal = producer.run(
            fixture_to_request(fixture, produced_at=produced_at, trace_id=trace_id),
            fixture_to_snapshot(fixture, produced_at=produced_at),
            trace_id=trace_id,
            now=produced_at,
        )
        reports.append(evaluate(signal, fixture, trace_id=trace_id))
    return reports
