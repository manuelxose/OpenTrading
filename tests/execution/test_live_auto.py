"""LIVE_AUTO execution-path tests (Phase 11).

Proves the automated path: a promoted strategy can trade without per-trade
human approval while every deterministic control (registry, Risk Engine
decision, emergency/kill switches, mode binding) still applies.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from core.domain.enums import EmergencyLevel, OperatingMode, StrategyState
from engines.execution.emergency import EmergencyControlViolation
from engines.execution.live_gate import LiveGateViolation, PriceContext
from engines.execution.service import ExecutionService
from engines.live_auto.config import LiveAutoConfig, LiveAutoViolation
from engines.live_auto.registry import InMemoryLiveAutoStore, LiveAutoRegistry

from execution_helpers import FakeReconcileClient, Stack, make_intent
from factories import make_risk_decision_approve


def _registry(stack: Stack) -> LiveAutoRegistry:
    return LiveAutoRegistry(
        InMemoryLiveAutoStore(),
        LiveAutoConfig(
            enabled=True,
            max_strategies=2,
            max_capital=Decimal("50000"),
            max_loss=Decimal("5000"),
            max_quote_age=timedelta(seconds=5),
            max_quantity=Decimal("1"),
        ),
        stack.clock,
        audit=stack.audit,
    )


def _promoted(stack: Stack, registry: LiveAutoRegistry) -> None:
    registry.promote(
        strategy_id="strategy-A",
        strategy_version="1.0.0",
        from_state=StrategyState.LIVE_GATED,
        risk_budget=Decimal("500"),
        capital_allocation=Decimal("10000"),
        actor="operator-1",
    )


def _service(
    stack: Stack, client: FakeReconcileClient, registry: LiveAutoRegistry
) -> ExecutionService:
    return ExecutionService(
        store=stack.store,
        applier=stack.applier,
        reconciler=stack.reconciler,
        controller=stack.controller,
        client=client,
        clock=stack.clock,
        audit=stack.audit,
        emergency=stack.emergency,
        live_auto=registry,
        operating_mode=OperatingMode.LIVE_AUTO,
    )


def _price(stack: Stack) -> PriceContext:
    return PriceContext(bid=Decimal("1.0800"), ask=Decimal("1.0802"), observed_at=stack.clock.now())


def _intent(stack: Stack) -> object:
    return make_intent(stack.clock.now(), operating_mode=OperatingMode.LIVE_AUTO)


def test_automated_order_requires_no_human_approval_and_is_persisted() -> None:
    stack = Stack()
    client = FakeReconcileClient()
    registry = _registry(stack)
    _promoted(stack, registry)
    service = _service(stack, client, registry)
    intent = _intent(stack)
    decision = make_risk_decision_approve(
        stack.clock.now(),
        decision_id=intent.risk_decision_id,
        approved_quantity=intent.quantity,
        risk_amount=Decimal("94.20"),
    )

    record = service.submit(intent, price_context=_price(stack), risk_decision=decision)

    assert len(client.submitted) == 1
    assert client.submitted[0]["live_intent"] is intent
    assert record.order_intent_id == intent.order_intent_id
    authorized = [
        e for e in stack.audit_sink.entries if e.action == "live_auto.order_authorized"
    ]
    assert len(authorized) == 1


def test_automated_order_without_risk_decision_fails_closed() -> None:
    stack = Stack()
    client = FakeReconcileClient()
    registry = _registry(stack)
    _promoted(stack, registry)
    service = _service(stack, client, registry)

    with pytest.raises(LiveGateViolation, match="Risk Engine"):
        service.submit(_intent(stack), price_context=_price(stack))
    assert client.submitted == []


def test_unpromoted_strategy_cannot_reach_the_venue() -> None:
    stack = Stack()
    client = FakeReconcileClient()
    registry = _registry(stack)  # nobody promoted
    service = _service(stack, client, registry)
    intent = _intent(stack)
    decision = make_risk_decision_approve(
        stack.clock.now(),
        decision_id=intent.risk_decision_id,
        approved_quantity=intent.quantity,
        risk_amount=Decimal("94.20"),
    )

    with pytest.raises(LiveAutoViolation, match="not in the LIVE_AUTO lifecycle state"):
        service.submit(intent, price_context=_price(stack), risk_decision=decision)
    assert client.submitted == []


def test_callers_cannot_smuggle_paper_mode_through_an_auto_runtime() -> None:
    stack = Stack()
    client = FakeReconcileClient()
    registry = _registry(stack)
    _promoted(stack, registry)
    service = _service(stack, client, registry)

    with pytest.raises(LiveGateViolation, match="authoritative execution mode"):
        service.submit(make_intent(stack.clock.now(), operating_mode=OperatingMode.PAPER))
    assert client.submitted == []


def test_emergency_kill_switch_remains_mandatory_in_auto_mode() -> None:
    stack = Stack()
    client = FakeReconcileClient()
    registry = _registry(stack)
    _promoted(stack, registry)
    service = _service(stack, client, registry)
    stack.emergency.activate(
        EmergencyLevel.NO_NEW_POSITIONS, actor="operator", reason="market halt"
    )
    intent = _intent(stack)
    decision = make_risk_decision_approve(
        stack.clock.now(),
        decision_id=intent.risk_decision_id,
        approved_quantity=intent.quantity,
        risk_amount=Decimal("94.20"),
    )

    with pytest.raises(EmergencyControlViolation, match="NO_NEW_POSITIONS"):
        service.submit(intent, price_context=_price(stack), risk_decision=decision)
    assert client.submitted == []


def test_stale_quote_is_refused_at_the_automated_gate() -> None:
    stack = Stack()
    client = FakeReconcileClient()
    registry = _registry(stack)
    _promoted(stack, registry)
    service = _service(stack, client, registry)
    intent = _intent(stack)
    decision = make_risk_decision_approve(
        stack.clock.now(),
        decision_id=intent.risk_decision_id,
        approved_quantity=intent.quantity,
        risk_amount=Decimal("94.20"),
    )
    stale = _price(stack)
    stack.clock.advance(timedelta(seconds=6))

    with pytest.raises(LiveAutoViolation, match="quote age"):
        service.submit(intent, price_context=stale, risk_decision=decision)
    assert client.submitted == []
