from datetime import UTC, datetime
from decimal import Decimal

import pytest
from apps.api.live_gated import build_live_gated_router
from apps.api.main import create_app
from core.clock.clocks import VirtualClock
from core.config.settings import Settings
from core.domain.enums import OperatingMode
from engines.execution.live_gate import (
    HumanApprovalGate,
    InMemoryApprovalStore,
    LiveGateConfig,
    PriceContext,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient

from factories import make_order_intent


def test_authenticated_operator_can_explicitly_approve() -> None:
    now = datetime(2026, 8, 28, 10, 0, tzinfo=UTC)
    gate = HumanApprovalGate(
        store=InMemoryApprovalStore(),
        clock=VirtualClock(now),
        signing_key=b"api-test-signing-key-is-32-bytes!",
        config=LiveGateConfig(broker_demo=True, max_live_quantity=Decimal("1")),
    )
    intent = make_order_intent(
        now,
        operating_mode=OperatingMode.LIVE_GATED,
        quantity=Decimal("0.01"),
    )
    gate.request_approval(
        intent,
        PriceContext(bid=Decimal("1.08"), ask=Decimal("1.081"), observed_at=now),
    )
    app = FastAPI()
    app.include_router(build_live_gated_router(gate, lambda: "human-operator"))

    response = TestClient(app).post(
        f"/api/v1/live-gated/approvals/{intent.order_intent_id}/approve", json={}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "APPROVED"
    assert body["approver_id"] == "human-operator"
    assert body["order_intent_id"] == str(intent.order_intent_id)
    assert body["risk_decision_id"] == str(intent.risk_decision_id)
    assert body["signature"]


def test_live_gated_api_fails_startup_without_secret_backed_configuration() -> None:
    with pytest.raises(RuntimeError, match="requires OT_LIVE_APPROVAL_SIGNING_KEY"):
        create_app(settings=Settings(operating_mode=OperatingMode.LIVE_GATED))
