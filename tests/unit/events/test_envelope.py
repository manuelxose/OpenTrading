"""Envelope tests: building, serializing, validating standard events (INV-15)."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest
from core.clock.clocks import VirtualClock
from core.events import (
    build_domain_event,
    deserialize_event,
    serialize_event,
)
from core.events.registry import UnknownEventError
from core.schemas import MarketSnapshot
from pydantic import ValidationError

from factories import (
    make_market_snapshot,
    make_order_intent,
    make_risk_decision_approve,
    make_risk_decision_reject,
    make_risk_decision_resize,
)


def test_build_market_snapshot_event(clock: VirtualClock) -> None:
    payload = make_market_snapshot(clock.now())
    event = build_domain_event(
        event_name="market.snapshot.created", payload=payload, clock=clock, producer="market-data"
    )
    assert event.event_name == "market.snapshot.created"
    assert event.producer == "market-data"
    assert event.event_time == clock.now()
    assert event.ingested_at == clock.now()
    assert event.payload == payload.canonical_dict()
    assert event.schema_version == "1.0.0"
    assert isinstance(event.event_id, UUID)


@pytest.mark.parametrize(
    ("event_name", "factory"),
    [
        ("risk.approved", make_risk_decision_approve),
        ("risk.resized", make_risk_decision_resize),
        ("risk.rejected", make_risk_decision_reject),
        ("order.intent.created", make_order_intent),
    ],
)
def test_build_other_events(event_name: str, factory: object, clock: VirtualClock) -> None:
    payload = factory(clock.now())  # type: ignore[operator]
    event = build_domain_event(
        event_name=event_name, payload=payload, clock=clock, producer="risk-engine"
    )
    assert event.event_name == event_name


def test_build_rejects_wrong_payload_class(clock: VirtualClock) -> None:
    payload = make_order_intent(clock.now())
    with pytest.raises(TypeError, match="must be a MarketSnapshot"):
        build_domain_event(
            event_name="market.snapshot.created",
            payload=payload,  # type: ignore[arg-type]
            clock=clock,
            producer="test",
        )


def test_build_rejects_unknown_event_name(clock: VirtualClock) -> None:
    payload = make_market_snapshot(clock.now())
    with pytest.raises(UnknownEventError):
        build_domain_event(
            event_name="market.snapshot.mystery", payload=payload, clock=clock, producer="test"
        )


def test_serialize_deserialize_round_trip(clock: VirtualClock) -> None:
    payload = make_market_snapshot(clock.now())
    event = build_domain_event(
        event_name="market.snapshot.created",
        payload=payload,
        clock=clock,
        producer="market-data",
        trace_id=UUID(int=42),
    )
    restored = deserialize_event(serialize_event(event))
    assert restored.model_dump(mode="json") == event.model_dump(mode="json")
    assert restored.trace_id == UUID(int=42)
    # Payload is re-validated against the registered contract.
    assert MarketSnapshot.model_validate(restored.payload).canonical_dict() == restored.payload


def test_deserialize_accepts_dict(clock: VirtualClock) -> None:
    payload = make_market_snapshot(clock.now())
    event = build_domain_event(
        event_name="market.snapshot.created", payload=payload, clock=clock, producer="test"
    )
    restored = deserialize_event(event.model_dump(mode="json"))
    assert restored.event_name == "market.snapshot.created"


def test_ingested_before_event_time_rejected(clock: VirtualClock) -> None:
    payload = make_market_snapshot(clock.now())
    event_time = clock.now()
    with pytest.raises(ValidationError, match="ingested_at"):
        build_domain_event(
            event_name="market.snapshot.created",
            payload=payload,
            clock=clock,
            producer="test",
            event_time=event_time,
            ingested_at=event_time - timedelta(seconds=1),
        )


def test_all_canonical_event_names_have_payloads() -> None:
    from core.events.registry import CANONICAL_EVENT_PAYLOAD_SCHEMAS

    expected = {
        "market.snapshot.created",
        "research.requested",
        "research.completed",
        "research.bundle.created",
        "quant.signal.created",
        "llm.signal.created",
        "signal.fused",
        "trade.proposal.created",
        "risk.approved",
        "risk.resized",
        "risk.rejected",
        "order.intent.created",
        "order.submitted",
        "order.acknowledged",
        "order.partially_filled",
        "order.filled",
        "order.cancelled",
        "order.rejected",
        "order.reconciled",
        "reconciliation.divergence",
        "system.safe_mode.entered",
        "system.safe_mode.exited",
        "system.emergency.activated",
        "system.emergency.deactivated",
        "system.emergency.heartbeat_lost",
        "system.emergency.heartbeat_restored",
        "position.updated",
        "trade.closed",
        "postmortem.completed",
        "memory.episode.created",
        "strategy.candidate.created",
        "strategy.promoted",
        "strategy.retired",
        "experiment.created",
        "experiment.completed",
    }
    assert set(CANONICAL_EVENT_PAYLOAD_SCHEMAS) == expected
