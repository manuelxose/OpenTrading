from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from adapters.mt4.client import Mt4ExecutionClient
from core.domain.enums import OperatingMode
from engines.execution.live_gate import (
    ApprovalStatus,
    HumanApprovalGate,
    InMemoryApprovalStore,
    KillScope,
    LiveGateConfig,
    LiveGateViolation,
    PriceContext,
)
from engines.execution.service import ExecutionService

from execution_helpers import FakeReconcileClient, Stack, make_intent
from factories import make_risk_decision_approve


def _price(stack: Stack, bid: str = "1.0800", ask: str = "1.0802") -> PriceContext:
    return PriceContext(bid=Decimal(bid), ask=Decimal(ask), observed_at=stack.clock.now())


def _gate(stack: Stack, *, ttl: int = 30, max_drift_bps: int = 10) -> HumanApprovalGate:
    return HumanApprovalGate(
        store=InMemoryApprovalStore(),
        clock=stack.clock,
        signing_key=b"test-signing-key-with-32-bytes!!",
        config=LiveGateConfig(
            approval_ttl=timedelta(seconds=ttl),
            max_price_drift_bps=Decimal(max_drift_bps),
            max_quote_age=timedelta(seconds=5),
            broker_demo=True,
            max_live_quantity=Decimal("1"),
        ),
    )


def _service(
    stack: Stack, client: FakeReconcileClient, gate: HumanApprovalGate
) -> ExecutionService:
    return ExecutionService(
        store=stack.store,
        applier=stack.applier,
        reconciler=stack.reconciler,
        controller=stack.controller,
        client=client,
        clock=stack.clock,
        live_gate=gate,
        operating_mode=OperatingMode.LIVE_GATED,
    )


def test_live_gated_never_reaches_mt4_without_explicit_approval() -> None:
    stack = Stack()
    client = FakeReconcileClient()
    gate = _gate(stack)
    service = _service(stack, client, gate)
    intent = make_intent(operating_mode=OperatingMode.LIVE_GATED)

    request = gate.request_approval(intent, _price(stack))
    assert request.status is ApprovalStatus.WAITING_FOR_HUMAN
    with pytest.raises(LiveGateViolation, match="explicit human approval"):
        service.submit(intent, price_context=_price(stack))
    assert client.submitted == []
    assert stack.store.get_order(intent.order_intent_id) is None


def test_live_deployment_rejects_caller_controlled_paper_mode() -> None:
    stack = Stack()
    client = FakeReconcileClient()
    service = _service(stack, client, _gate(stack))

    with pytest.raises(LiveGateViolation, match="authoritative execution mode"):
        service.submit(make_intent(operating_mode=OperatingMode.PAPER))
    assert client.submitted == []


def test_valid_approval_is_bound_and_consumed_once() -> None:
    stack = Stack()
    client = FakeReconcileClient()
    gate = _gate(stack)
    service = _service(stack, client, gate)
    intent = make_intent(operating_mode=OperatingMode.LIVE_GATED)
    price = _price(stack)

    gate.request_approval(intent, price)
    approval = gate.approve(intent.order_intent_id, approver_id="operator@example.test")
    assert approval.order_intent_id == intent.order_intent_id
    assert approval.risk_decision_id == intent.risk_decision_id
    assert approval.strategy_version == intent.strategy_version
    assert approval.price_context == price
    assert approval.signature

    service.submit(intent, price_context=price)
    assert len(client.submitted) == 1

    with pytest.raises(LiveGateViolation, match="approval lifecycle already exists"):
        gate.request_approval(intent, price)
    with pytest.raises(LiveGateViolation, match="already consumed"):
        service.submit(intent, price_context=price)
    assert len(client.submitted) == 1


def test_expired_approval_never_reaches_mt4() -> None:
    stack = Stack()
    client = FakeReconcileClient()
    gate = _gate(stack, ttl=2)
    service = _service(stack, client, gate)
    intent = make_intent(operating_mode=OperatingMode.LIVE_GATED)
    gate.request_approval(intent, _price(stack))
    gate.approve(intent.order_intent_id, approver_id="operator")
    stack.clock.advance(timedelta(seconds=3))

    with pytest.raises(LiveGateViolation, match="expired"):
        service.submit(intent, price_context=_price(stack))
    assert client.submitted == []


def test_material_market_change_requires_revalidation_and_new_approval() -> None:
    stack = Stack()
    client = FakeReconcileClient()
    gate = _gate(stack, max_drift_bps=5)
    service = _service(stack, client, gate)
    intent = make_intent(operating_mode=OperatingMode.LIVE_GATED)
    gate.request_approval(intent, _price(stack))
    gate.approve(intent.order_intent_id, approver_id="operator")
    changed = _price(stack, bid="1.0900", ask="1.0902")

    with pytest.raises(LiveGateViolation, match="risk revalidation"):
        service.submit(intent, price_context=changed)
    assert client.submitted == []

    new_decision_id = uuid4()
    revalidated_intent = intent.model_copy(update={"risk_decision_id": new_decision_id})
    gate.revalidate(
        intent.order_intent_id,
        intent=revalidated_intent,
        risk_decision=make_risk_decision_approve(stack.clock.now(), decision_id=new_decision_id),
        price_context=changed,
    )
    with pytest.raises(LiveGateViolation, match="explicit human approval"):
        service.submit(revalidated_intent, price_context=changed)
    gate.approve(intent.order_intent_id, approver_id="operator")
    service.submit(revalidated_intent, price_context=changed)
    assert len(client.submitted) == 1


def test_tampering_and_emergency_kill_fail_closed() -> None:
    stack = Stack()
    client = FakeReconcileClient()
    gate = _gate(stack)
    service = _service(stack, client, gate)
    intent = make_intent(operating_mode=OperatingMode.LIVE_GATED)
    price = _price(stack)
    gate.request_approval(intent, price)
    gate.approve(intent.order_intent_id, approver_id="operator")

    tampered = intent.model_copy(update={"strategy_version": "evil"})
    with pytest.raises(LiveGateViolation, match="does not match"):
        service.submit(tampered, price_context=price)
    quantity_tampered = intent.model_copy(update={"quantity": Decimal("0.20")})
    with pytest.raises(LiveGateViolation, match="does not match"):
        service.submit(quantity_tampered, price_context=price)
    gate.activate_kill(KillScope.EMERGENCY, actor="incident-commander", reason="incident")
    with pytest.raises(LiveGateViolation, match="kill switch"):
        service.submit(intent, price_context=price)
    assert client.submitted == []


def test_tampered_approval_signature_fails_closed() -> None:
    stack = Stack()
    store = InMemoryApprovalStore()
    gate = HumanApprovalGate(
        store=store,
        clock=stack.clock,
        signing_key=b"test-signing-key-with-32-bytes!!",
        config=LiveGateConfig(broker_demo=True, max_live_quantity=Decimal("1")),
    )
    intent = make_intent(operating_mode=OperatingMode.LIVE_GATED)
    price = _price(stack)
    gate.request_approval(intent, price)
    approved = gate.approve(intent.order_intent_id, approver_id="operator")
    store.put(replace(approved, signature="0" * 64))

    with pytest.raises(LiveGateViolation, match="signature verification"):
        gate.consume(intent, price)


def test_real_account_requires_deliberately_tiny_configured_exposure() -> None:
    stack = Stack()
    gate = HumanApprovalGate(
        store=InMemoryApprovalStore(),
        clock=stack.clock,
        signing_key=b"test-signing-key-with-32-bytes!!",
        config=LiveGateConfig(broker_demo=False, max_live_quantity=Decimal("0.01")),
    )
    intent = make_intent(
        operating_mode=OperatingMode.LIVE_GATED,
        quantity=Decimal("0.10"),
    )
    with pytest.raises(LiveGateViolation, match="tiny live exposure"):
        gate.request_approval(intent, _price(stack))


def test_mt4_client_itself_refuses_unguarded_live_gated_configuration() -> None:
    with pytest.raises(ValueError, match="requires a live approval authorizer"):
        Mt4ExecutionClient(operating_mode=OperatingMode.LIVE_GATED)


def test_mt4_client_itself_refuses_unguarded_live_auto_configuration() -> None:
    with pytest.raises(ValueError, match="requires a live order authorizer"):
        Mt4ExecutionClient(operating_mode=OperatingMode.LIVE_AUTO)


def test_mt4_client_checks_consumed_approval_before_transport() -> None:
    stack = Stack()
    gate = _gate(stack)
    intent = make_intent(operating_mode=OperatingMode.LIVE_GATED)
    client = Mt4ExecutionClient(
        clock=stack.clock,
        operating_mode=OperatingMode.LIVE_GATED,
        live_authorizer=gate.assert_consumed_authorization,
    )

    with pytest.raises(LiveGateViolation, match="explicit human approval"):
        client.submit_order(
            order_intent_id=intent.order_intent_id,
            strategy_id=intent.strategy_id,
            strategy_version=intent.strategy_version,
            symbol=intent.instrument_id,
            side=intent.side,
            quantity=intent.quantity,
            order_type=intent.order_type,
            max_slippage=intent.max_slippage,
            live_intent=intent,
        )
