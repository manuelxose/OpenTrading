"""API tests: health and contract catalog endpoints (no trading logic)."""

from __future__ import annotations

from apps.api.main import create_app
from core.clock.clocks import VirtualClock
from core.config.settings import Settings
from core.observability.metrics import OperationalMetrics
from fastapi.testclient import TestClient
from prometheus_client import CollectorRegistry

from factories import FIXED_START


def _client() -> TestClient:
    app = create_app(
        settings=Settings(operating_mode="PAPER"),  # type: ignore[arg-type]
        clock=VirtualClock(FIXED_START),
    )
    return TestClient(app)


def test_healthz() -> None:
    response = _client().get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["operating_mode"] == "PAPER"
    assert body["schema_version"] == "1.0.0"
    assert body["now"] == FIXED_START.isoformat()


def test_contracts_catalog() -> None:
    response = _client().get("/api/v1/contracts")
    assert response.status_code == 200
    contracts = response.json()["contracts"]
    names = {contract["name"] for contract in contracts}
    assert {
        "Instrument",
        "MarketSnapshot",
        "ResearchRequest",
        "ResearchPacket",
        "QuantSignal",
        "LLMSignal",
        "FusedSignal",
        "TradeProposal",
        "RiskDecision",
        "OrderIntent",
        "ExecutionReport",
        "PositionSnapshot",
        "TradeOutcome",
        "PostTradeReview",
        "MemoryEpisode",
        "FactorCandidate",
        "ModelCandidate",
        "StrategyCandidate",
        "ExperimentRun",
        "PromotionDecision",
        "DomainEvent",
    } <= names
    assert all(contract["schema_version"] == "1.0.0" for contract in contracts)


def test_metrics_endpoint_exposes_service_health() -> None:
    operational_metrics = OperationalMetrics(registry=CollectorRegistry())
    app = create_app(
        settings=Settings(operating_mode="PAPER"),  # type: ignore[arg-type]
        clock=VirtualClock(FIXED_START),
        operational_metrics=operational_metrics,
    )
    client = TestClient(app)

    client.get("/healthz")
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "opentrading_service_health" in response.text
