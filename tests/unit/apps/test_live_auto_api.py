"""Operator API tests for LIVE_AUTO governance (Phase 11)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from apps.api.live_auto import build_live_auto_router
from apps.api.main import create_app
from core.audit.audit import AuditLogger, InMemoryAuditSink
from core.clock.clocks import VirtualClock
from core.config.settings import Settings
from core.domain.enums import OperatingMode
from engines.live_auto.config import LiveAutoConfig
from engines.live_auto.registry import InMemoryLiveAutoStore, LiveAutoRegistry
from fastapi import FastAPI, Header, HTTPException, status
from fastapi.testclient import TestClient

T0 = datetime(2026, 8, 29, 9, 0, 0, tzinfo=UTC)
AUTH = {"Authorization": "Bearer opentrading-test-operator-token-0123456789abcdef"}


def authenticated_operator(
    authorization: str = Header(default=""),
) -> str:
    if authorization != "Bearer opentrading-test-operator-token-0123456789abcdef":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return "operator-1"


def make_registry(
    config: LiveAutoConfig | None = None,
) -> tuple[LiveAutoRegistry, InMemoryAuditSink]:
    clock = VirtualClock(T0)
    sink = InMemoryAuditSink()
    registry = LiveAutoRegistry(
        InMemoryLiveAutoStore(),
        config
        or LiveAutoConfig(
            enabled=True,
            max_strategies=2,
            max_capital=Decimal("50000"),
            max_loss=Decimal("5000"),
            max_quote_age=timedelta(seconds=5),
        ),
        clock,
        audit=AuditLogger(sink, clock),
    )
    return registry, sink


def app_with(registry: LiveAutoRegistry) -> FastAPI:
    app = FastAPI()
    app.include_router(build_live_auto_router(registry, authenticated_operator))
    return app


def promotion_body(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "strategy_id": "strategy-01",
        "strategy_version": "1.0.0",
        "from_state": "LIVE_GATED",
        "risk_budget": "500",
        "capital_allocation": "10000",
    }
    base.update(overrides)
    return base


def test_operator_can_promote_live_gated_strategy_with_audit_event() -> None:
    registry, sink = make_registry()
    client = TestClient(app_with(registry))

    response = client.post("/api/v1/live-auto/promotions", json=promotion_body(), headers=AUTH)

    assert response.status_code == 201
    body = response.json()
    assert body["strategy_id"] == "strategy-01"
    assert body["from_state"] == "LIVE_GATED"
    assert body["state"] == "LIVE_AUTO"
    assert body["promoted_by"] == "operator-1"
    assert [e.action for e in sink.entries] == ["live_auto.strategy_promoted"]


def test_promotion_requires_operator_authentication() -> None:
    registry, sink = make_registry()
    client = TestClient(app_with(registry))

    response = client.post("/api/v1/live-auto/promotions", json=promotion_body())

    assert response.status_code in (401, 403)
    assert sink.entries == []


def test_promotion_from_non_live_gated_state_is_rejected() -> None:
    registry, _ = make_registry()
    client = TestClient(app_with(registry))

    response = client.post(
        "/api/v1/live-auto/promotions",
        json=promotion_body(from_state="PAPER"),
        headers=AUTH,
    )

    assert response.status_code == 409
    assert "LIVE_GATED" in response.json()["detail"]


def test_promotion_is_rejected_while_capability_is_disabled() -> None:
    registry, _ = make_registry(LiveAutoConfig())  # disabled by default
    client = TestClient(app_with(registry))

    response = client.post("/api/v1/live-auto/promotions", json=promotion_body(), headers=AUTH)

    assert response.status_code == 409
    assert "disabled" in response.json()["detail"]


def test_demote_and_pnl_endpoints_are_operator_only_and_audited() -> None:
    registry, sink = make_registry()
    client = TestClient(app_with(registry))
    client.post("/api/v1/live-auto/promotions", json=promotion_body(), headers=AUTH)

    demote = client.post(
        "/api/v1/live-auto/strategies/strategy-01/demote",
        json={"reason": "degradation"},
        headers=AUTH,
    )
    assert demote.status_code == 200
    assert demote.json()["active"] is False

    pnl = client.post(
        "/api/v1/live-auto/pnl",
        json={"strategy_id": "strategy-01", "amount": "-250", "source": "posttrade"},
        headers=AUTH,
    )
    assert pnl.status_code == 201
    assert pnl.json()["total_realized_pnl"] == "-250"
    assert {e.action for e in sink.entries} == {
        "live_auto.strategy_promoted",
        "live_auto.strategy_demoted",
        "live_auto.pnl_recorded",
    }


def test_live_auto_api_fails_startup_without_operator_token() -> None:
    with pytest.raises(RuntimeError, match="requires OT_LIVE_OPERATOR_TOKEN"):
        create_app(
            settings=Settings(
                operating_mode=OperatingMode.LIVE_AUTO,
                live_auto_enabled=True,
                live_auto_max_strategies=1,
                live_auto_max_capital=Decimal("10000"),
                live_auto_max_loss=Decimal("1000"),
            )
        )


def test_live_gated_mode_still_mounts_live_auto_governance() -> None:
    registry, _ = make_registry()
    app = create_app(
        settings=Settings(
            operating_mode=OperatingMode.LIVE_GATED,
            live_approval_signing_key="x" * 32,
            live_operator_token="opentrading-test-operator-token-0123456789abcdef",
            live_max_quantity=Decimal("0.01"),
        ),
        live_auto_registry=registry,
    )
    response = TestClient(app).get("/api/v1/live-auto/status", headers=AUTH)
    assert response.status_code == 200
    assert response.json()["enabled"] is True


def test_operating_mode_cannot_be_changed_via_the_api() -> None:
    registry, _ = make_registry()
    client = TestClient(app_with(registry))
    for method in ("post", "put", "patch"):
        for path in (
            "/api/v1/live-auto/mode",
            "/api/v1/operating-mode",
            "/api/v1/live-auto/strategies/strategy-01/state",
        ):
            response = getattr(client, method)(path, json={"mode": "LIVE_GATED"}, headers=AUTH)
            assert response.status_code in (404, 405, 422), (method, path, response.status_code)
