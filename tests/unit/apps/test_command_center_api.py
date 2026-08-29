from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from apps.api.command_center import CommandCenterDataSource, PostgresCommandCenterDataSource
from apps.api.main import create_app
from core.config.settings import Settings
from fastapi.testclient import TestClient


class StubCommandCenterDataSource(CommandCenterDataSource):
    def overview(self, now: datetime) -> dict[str, Any]:
        return {
            "asOf": now.isoformat(),
            "account": {"nav": "100200", "equity": "100200", "currency": "USD"},
            "performance": {"pnl": "200", "drawdownPct": 0.4},
            "exposure": {"gross": "12000", "net": "4000"},
            "riskStatus": "NORMAL",
            "mt4Status": "CONNECTED",
            "dataFreshness": {"status": "FRESH", "latestAt": now.isoformat()},
        }

    def collection(self, resource: str, limit: int) -> dict[str, Any]:
        return {"resource": resource, "items": [], "total": 0, "limit": limit}

    def risk(self) -> dict[str, Any]:
        return {
            "configuredLimits": [],
            "currentUtilization": [],
            "recentRejections": [],
            "killSwitch": {"active": False, "reasonCodes": []},
        }

    def trade_detail(self, trade_id: str) -> dict[str, Any] | None:
        if trade_id != "trade-1":
            return None
        return {
            "tradeId": trade_id,
            "traceId": "trace-1",
            "stages": [
                {"key": "sourceData", "status": "AVAILABLE", "payload": {"symbol": "EURUSD"}},
                {"key": "riskDecision", "status": "AVAILABLE", "payload": {"decision": "APPROVE"}},
            ],
        }


def client() -> TestClient:
    return TestClient(
        create_app(
            settings=Settings(),
            readiness_checks=[],
            command_center_data_source=StubCommandCenterDataSource(),
        )
    )


def test_overview_is_a_real_versioned_read_model() -> None:
    response = client().get("/api/v1/command-center/overview")
    assert response.status_code == 200
    assert response.json()["data"]["account"]["nav"] == "100200"
    assert response.json()["schemaVersion"] == "1.0.0"


def test_collections_are_bounded() -> None:
    response = client().get("/api/v1/command-center/orders?limit=999")
    assert response.status_code == 422


def test_trade_detail_reconstructs_stages_and_404s_unknown_ids() -> None:
    response = client().get("/api/v1/command-center/trades/trade-1")
    assert [stage["key"] for stage in response.json()["data"]["stages"]] == [
        "sourceData",
        "riskDecision",
    ]
    assert client().get("/api/v1/command-center/trades/missing").status_code == 404


def test_system_endpoint_includes_dependency_results() -> None:
    response = client().get("/api/v1/command-center/system")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "HEALTHY"


class Row(SimpleNamespace):
    @property
    def _mapping(self) -> dict[str, Any]:
        return vars(self)


class Result:
    def __init__(self, *, first: Any = None, rows: list[Any] | None = None) -> None:
        self.value = first
        self.rows = rows or []

    def first(self) -> Any:
        return self.value

    def all(self) -> list[Any]:
        return self.rows


class Connection:
    def __init__(self, results: list[Result]) -> None:
        self.results = results

    def __enter__(self) -> Connection:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, _query: object) -> Result:
        return self.results.pop(0)


class Engine:
    def __init__(self, results: list[Result]) -> None:
        self.results = results

    def connect(self) -> Connection:
        return Connection(self.results)


def test_postgres_trade_detail_always_projects_the_nine_required_stages() -> None:
    trade_id, trace_id, intent_id = uuid4(), uuid4(), uuid4()
    review = Row(trade_id=trade_id, trace_id=trace_id, review_payload={"verdict": "sound"})
    lifecycle = Row(
        trade_id=trade_id,
        trace_id=trace_id,
        order_intent_id=intent_id,
        state="REVIEWED",
    )
    context = Row(
        fragments={
            "source_data": {"instrument_id": "EURUSD"},
            "llm": {"direction": "LONG"},
            "quant": {"direction": "LONG"},
            "fused": {"direction": "LONG"},
            "risk_decision": {"decision": "APPROVE"},
            "order_intent": {"order_intent_id": str(intent_id)},
        }
    )
    order = Row(order_intent_id=intent_id, state="FILLED")
    source = PostgresCommandCenterDataSource(
        Settings(),
        engine=Engine(  # type: ignore[arg-type]
            [
                Result(first=review),
                Result(first=lifecycle),
                Result(first=context),
                Result(first=order),
            ]
        ),
    )

    detail = source.trade_detail(str(trade_id))

    assert detail is not None
    assert [stage["key"] for stage in detail["stages"]] == [
        "sourceData",
        "tradingAgentsAnalysis",
        "quantSignal",
        "fusedSignal",
        "riskDecision",
        "orderIntent",
        "brokerExecution",
        "positionLifecycle",
        "postmortem",
    ]
    assert all(stage["status"] == "AVAILABLE" for stage in detail["stages"])


def test_postgres_risk_projects_policy_utilization_and_breaches() -> None:
    positions = [Row(quantity=3, average_entry_price=200_000)]
    portfolio_context = Row(
        fragments={
            "portfolio_snapshot": {
                "as_of": datetime.now().isoformat(),
                "gross_exposure": "600000",
                "net_exposure": "600000",
                "equity": "100000",
                "peak_equity": "110000",
                "daily_loss": "1200",
                "drawdown": "0.090909",
            }
        }
    )
    source = PostgresCommandCenterDataSource(
        Settings(),
        engine=Engine(
            [
                Result(),
                Result(rows=positions),
                Result(rows=[]),
                Result(rows=[portfolio_context]),
            ]
        ),  # type: ignore[arg-type]
    )

    risk = source.risk()

    keys = {limit["key"] for limit in risk["configuredLimits"]}
    assert {"maxRiskPerTrade", "maxTotalExposure", "maxDailyLoss", "maxDrawdownPct"} <= keys
    assert risk["currentUtilization"]
    assert {breach["key"] for breach in risk["breaches"]} >= {"totalExposure", "dailyLoss"}


def test_risk_equality_boundaries_match_deterministic_engine() -> None:
    daily = PostgresCommandCenterDataSource._utilization(
        "dailyLoss", Decimal("1000"), Decimal("1000"), inclusive=True
    )
    drawdown = PostgresCommandCenterDataSource._utilization(
        "drawdown", Decimal("0.20"), Decimal("0.20"), inclusive=True
    )
    exposure = PostgresCommandCenterDataSource._utilization(
        "totalExposure", Decimal("500000"), Decimal("500000")
    )

    assert daily["isBreached"] is True
    assert drawdown["isBreached"] is True
    assert exposure["isBreached"] is False


def test_overview_drawdown_uses_clamped_canonical_snapshot() -> None:
    now = datetime.now()
    account = Row(
        equity=120_000,
        peak_equity=100_000,
        currency="USD",
        daily_pnl=20_000,
        realized_pnl=20_000,
    )
    context = Row(
        fragments={
            "portfolio_snapshot": {
                "as_of": now.isoformat(),
                "gross_exposure": "0",
                "net_exposure": "0",
                "drawdown": "0",
            }
        }
    )
    dataset = Row(available_time_max=now)
    source = PostgresCommandCenterDataSource(
        Settings(),
        engine=Engine(  # type: ignore[arg-type]
            [
                Result(first=account),
                Result(),
                Result(),
                Result(rows=[context]),
                Result(first=dataset),
            ]
        ),
    )

    overview = source.overview(now)

    assert overview["performance"]["drawdownPct"] == 0
