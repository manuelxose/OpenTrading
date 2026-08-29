"""LIVE_AUTO governance registry tests (Phase 11).

Covers the deterministic authorizer and the promotion/demotion/PnL governance
actions with an in-memory store and a fully recorded audit trail.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from core.audit.audit import AuditLogger, InMemoryAuditSink
from core.clock.clocks import VirtualClock
from core.domain.enums import OperatingMode, RiskDecisionType, StrategyState
from engines.execution.live_gate import PriceContext
from engines.live_auto.config import LiveAutoConfig, LiveAutoViolation
from engines.live_auto.registry import InMemoryLiveAutoStore, LiveAutoRegistry

from factories import (
    make_order_intent,
    make_risk_decision_approve,
    make_risk_decision_reject,
    make_risk_decision_resize,
)

T0 = datetime(2026, 8, 29, 9, 0, 0, tzinfo=UTC)


def enabled_config(**overrides: object) -> LiveAutoConfig:
    base: dict[str, object] = {
        "enabled": True,
        "max_strategies": 3,
        "max_capital": Decimal("50000"),
        "max_loss": Decimal("5000"),
        "max_quote_age": timedelta(seconds=5),
        "max_quantity": Decimal("1"),
    }
    base.update(overrides)
    return LiveAutoConfig(**base)  # type: ignore[arg-type]


def make_registry(
    config: LiveAutoConfig | None = None,
) -> tuple[LiveAutoRegistry, InMemoryAuditSink]:
    clock = VirtualClock(T0)
    sink = InMemoryAuditSink()
    registry = LiveAutoRegistry(
        InMemoryLiveAutoStore(),
        config or enabled_config(),
        clock,
        audit=AuditLogger(sink, clock),
    )
    return registry, sink


def promote(registry: LiveAutoRegistry, strategy_id: str = "strategy-01") -> None:
    registry.promote(
        strategy_id=strategy_id,
        strategy_version="1.0.0",
        from_state=StrategyState.LIVE_GATED,
        risk_budget=Decimal("500"),
        capital_allocation=Decimal("10000"),
        actor="operator-1",
        evidence=("backtest-report:v2",),
    )


def intent_for(
    registry: LiveAutoRegistry,
    strategy_id: str = "strategy-01",
    **overrides: object,
):
    base: dict[str, object] = {
        "strategy_id": strategy_id,
        "operating_mode": OperatingMode.LIVE_AUTO,
        "quantity": Decimal("0.10"),
    }
    base.update(overrides)
    return make_order_intent(T0, **base)


def decision_for(
    intent,
    *,
    decision_type: RiskDecisionType = RiskDecisionType.APPROVE,
    risk_amount: Decimal = Decimal("94.20"),
):
    maker = {
        RiskDecisionType.APPROVE: make_risk_decision_approve,
        RiskDecisionType.REJECT: make_risk_decision_reject,
        RiskDecisionType.RESIZE: make_risk_decision_resize,
    }[decision_type]
    if decision_type is RiskDecisionType.REJECT:
        return maker(T0, decision_id=intent.risk_decision_id)
    return maker(
        T0,
        decision_id=intent.risk_decision_id,
        approved_quantity=intent.quantity,
        risk_amount=risk_amount,
    )


def price(observed_at: datetime = T0) -> PriceContext:
    return PriceContext(bid=Decimal("1.0800"), ask=Decimal("1.0802"), observed_at=observed_at)


# ── Capability is disabled by default ────────────────────────────────────────


def test_live_auto_is_disabled_by_default() -> None:
    config = LiveAutoConfig()
    assert config.enabled is False
    registry, _ = make_registry(config)
    intent = intent_for(registry)
    with pytest.raises(LiveAutoViolation, match="disabled"):
        registry.assert_submission_authorized(
            intent=intent, risk_decision=decision_for(intent), price_context=price()
        )
    with pytest.raises(LiveAutoViolation, match="disabled"):
        promote(registry)


def test_disabled_or_partial_config_fails_closed_on_runtime_wiring() -> None:
    with pytest.raises(LiveAutoViolation):
        LiveAutoConfig(enabled=True).assert_enabled()  # no ceilings configured
    with pytest.raises(LiveAutoViolation):
        LiveAutoConfig(
            enabled=True, max_strategies=2, max_capital=Decimal("1"), max_loss=None
        ).assert_enabled()


# ── Promotion governance ─────────────────────────────────────────────────────


def test_promotion_requires_explicit_live_gated_source_state() -> None:
    registry, _ = make_registry()
    for bad_state in (StrategyState.PAPER, StrategyState.SHADOW, StrategyState.LIVE_AUTO):
        with pytest.raises(LiveAutoViolation, match="LIVE_GATED"):
            registry.promote(
                strategy_id="strategy-01",
                strategy_version="1.0.0",
                from_state=bad_state,
                risk_budget=Decimal("500"),
                capital_allocation=Decimal("10000"),
                actor="operator-1",
            )


def test_promotion_writes_an_immutable_audit_event() -> None:
    registry, sink = make_registry()
    promote(registry)
    promoted = [e for e in sink.entries if e.action == "live_auto.strategy_promoted"]
    assert len(promoted) == 1
    entry = promoted[0]
    assert entry.actor == "operator-1"
    assert entry.target == "strategy-01"
    assert entry.metadata["from_state"] == StrategyState.LIVE_GATED.value
    assert entry.metadata["to_state"] == StrategyState.LIVE_AUTO.value
    assert entry.metadata["risk_budget"] == "500"
    assert entry.timestamp == T0


def test_promotion_is_idempotence_guarded() -> None:
    registry, _ = make_registry()
    promote(registry)
    with pytest.raises(LiveAutoViolation, match="already in LIVE_AUTO"):
        promote(registry)


def test_promotion_enforces_strategy_and_capital_ceilings() -> None:
    registry, _ = make_registry(enabled_config(max_strategies=1, max_capital=Decimal("15000")))
    promote(registry)
    with pytest.raises(LiveAutoViolation, match="ceiling reached"):
        promote(registry, strategy_id="strategy-02")
    # Capital ceiling: a second strategy fits the count but not the capital.
    registry, _ = make_registry(enabled_config(max_strategies=2, max_capital=Decimal("15000")))
    promote(registry)  # 10000 allocated
    with pytest.raises(LiveAutoViolation, match="capital allocation"):
        registry.promote(
            strategy_id="strategy-02",
            strategy_version="1.0.0",
            from_state=StrategyState.LIVE_GATED,
            risk_budget=Decimal("500"),
            capital_allocation=Decimal("6000"),
            actor="operator-1",
        )


def test_promotion_respects_configured_risk_budget_ceiling() -> None:
    registry, _ = make_registry(
        enabled_config(strategy_risk_budget_ceilings={"strategy-01": Decimal("200")})
    )
    with pytest.raises(LiveAutoViolation, match="ceiling"):
        promote(registry)  # budget 500 > ceiling 200


def test_demote_revokes_live_auto_authority_and_is_audited() -> None:
    registry, sink = make_registry()
    promote(registry)
    intent = intent_for(registry)
    registry.assert_submission_authorized(
        intent=intent, risk_decision=decision_for(intent), price_context=price()
    )
    registry.demote(strategy_id="strategy-01", actor="operator-2", reason="degradation")
    with pytest.raises(LiveAutoViolation, match="not in the LIVE_AUTO lifecycle state"):
        registry.assert_submission_authorized(
            intent=intent, risk_decision=decision_for(intent), price_context=price()
        )
    assert any(
        e.action == "live_auto.strategy_demoted" and e.actor == "operator-2"
        for e in sink.entries
    )


# ── Automated-order authorization ────────────────────────────────────────────


def test_only_live_auto_lifecycle_strategies_may_trade() -> None:
    registry, _ = make_registry()
    intent = intent_for(registry)
    with pytest.raises(LiveAutoViolation, match="not in the LIVE_AUTO lifecycle state"):
        registry.assert_submission_authorized(
            intent=intent, risk_decision=decision_for(intent), price_context=price()
        )
    promote(registry)
    # A PAPER-mode intent can never reach the automated path.
    with pytest.raises(LiveAutoViolation, match="only LIVE_AUTO OrderIntents"):
        registry.assert_submission_authorized(
            intent=intent_for(registry, operating_mode=OperatingMode.PAPER),
            risk_decision=decision_for(intent),
            price_context=price(),
        )


def test_risk_engine_is_mandatory_and_bound_to_the_intent() -> None:
    registry, _ = make_registry()
    promote(registry)
    intent = intent_for(registry)
    with pytest.raises(LiveAutoViolation, match="APPROVE/RESIZE"):
        registry.assert_submission_authorized(
            intent=intent,
            risk_decision=decision_for(intent, decision_type=RiskDecisionType.REJECT),
            price_context=price(),
        )
    with pytest.raises(LiveAutoViolation, match="risk_decision_id"):
        registry.assert_submission_authorized(
            intent=intent,
            risk_decision=make_risk_decision_approve(
                T0, approved_quantity=intent.quantity, risk_amount=Decimal("10")
            ),
            price_context=price(),
        )
    with pytest.raises(LiveAutoViolation, match="approved_quantity"):
        registry.assert_submission_authorized(
            intent=intent,
            risk_decision=make_risk_decision_approve(
                T0,
                decision_id=intent.risk_decision_id,
                approved_quantity=Decimal("0.5"),
                risk_amount=Decimal("10"),
            ),
            price_context=price(),
        )


def test_resize_decisions_are_accepted_when_quantities_match_exactly() -> None:
    registry, sink = make_registry()
    promote(registry)
    intent = intent_for(registry)
    registry.assert_submission_authorized(
        intent=intent,
        risk_decision=decision_for(intent, decision_type=RiskDecisionType.RESIZE),
        price_context=price(),
    )
    assert any(e.action == "live_auto.order_authorized" for e in sink.entries)


def test_risk_budget_binds_automated_orders() -> None:
    registry, _ = make_registry()
    promote(registry)  # budget 500
    intent = intent_for(registry)
    with pytest.raises(LiveAutoViolation, match="risk budget"):
        registry.assert_submission_authorized(
            intent=intent,
            risk_decision=decision_for(intent, risk_amount=Decimal("501")),
            price_context=price(),
        )


def test_global_loss_limit_blocks_new_entries() -> None:
    registry, sink = make_registry(enabled_config(max_loss=Decimal("1000")))
    promote(registry)
    registry.record_realized_pnl(
        strategy_id="strategy-01", amount=Decimal("-1000"), actor="ops", source="posttrade"
    )
    intent = intent_for(registry)
    with pytest.raises(LiveAutoViolation, match="loss limit"):
        registry.assert_submission_authorized(
            intent=intent, risk_decision=decision_for(intent), price_context=price()
        )
    assert any(e.action == "live_auto.order_denied" for e in sink.entries)
    # A loss that only reaches the limit leaves the door open.
    registry_2, _ = make_registry(enabled_config(max_loss=Decimal("1000")))
    promote(registry_2)
    registry_2.record_realized_pnl(
        strategy_id="strategy-01", amount=Decimal("-999"), actor="ops", source="posttrade"
    )
    intent_2 = intent_for(registry_2)
    registry_2.assert_submission_authorized(
        intent=intent_2,
        risk_decision=decision_for(intent_2),
        price_context=price(),
    )


def test_quote_freshness_and_quantity_ceilings_stay_mandatory() -> None:
    registry, _ = make_registry()
    promote(registry)
    intent = intent_for(registry)
    with pytest.raises(LiveAutoViolation, match="quote age"):
        registry.assert_submission_authorized(
            intent=intent,
            risk_decision=decision_for(intent),
            price_context=price(observed_at=T0 - timedelta(seconds=10)),
        )
    big_intent = intent_for(registry, quantity=Decimal("2"))
    with pytest.raises(LiveAutoViolation, match="quantity ceiling"):
        registry.assert_submission_authorized(
            intent=big_intent,
            risk_decision=decision_for(big_intent),
            price_context=price(),
        )


def test_authorized_automated_order_is_fully_audited() -> None:
    registry, sink = make_registry()
    promote(registry)
    intent = intent_for(registry)
    decision = decision_for(intent)
    registry.assert_submission_authorized(
        intent=intent, risk_decision=decision, price_context=price()
    )
    authorized = [e for e in sink.entries if e.action == "live_auto.order_authorized"]
    assert len(authorized) == 1
    entry = authorized[0]
    assert entry.target == "strategy-01"
    assert entry.metadata["order_intent_id"] == str(intent.order_intent_id)
    assert entry.metadata["risk_decision_id"] == str(intent.risk_decision_id)
    assert entry.metadata["risk_amount"] == "94.20"
    assert entry.metadata["risk_budget"] == "500"


def test_wire_authorizer_rechecks_registry_state() -> None:
    registry, _ = make_registry()
    promote(registry)
    intent = intent_for(registry)
    registry.assert_wire_authorized(intent=intent)
    registry.demote(strategy_id="strategy-01", actor="operator", reason="stop")
    with pytest.raises(LiveAutoViolation, match="not in the LIVE_AUTO lifecycle state"):
        registry.assert_wire_authorized(intent=intent)


def test_pnl_ledger_requires_registry_membership_and_is_append_only() -> None:
    registry, _ = make_registry()
    with pytest.raises(LiveAutoViolation, match="not in the LIVE_AUTO registry"):
        registry.record_realized_pnl(
            strategy_id="strategy-01", amount=Decimal("-10"), actor="ops", source="posttrade"
        )
    promote(registry)
    registry.record_realized_pnl(
        strategy_id="strategy-01", amount=Decimal("-250"), actor="ops", source="posttrade"
    )
    registry.record_realized_pnl(
        strategy_id="strategy-01", amount=Decimal("80"), actor="ops", source="posttrade"
    )
    assert registry.status()["realized_pnl"] == "-170"
