"""Event versioning tests: payload upgrade chains and old-envelope deserialization."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import pytest
from core.clock.clocks import VirtualClock
from core.events import deserialize_event, upgrade_payload
from core.events.upgrades import UpgradeNotFoundError
from core.schemas import MarketSnapshot

from factories import FIXED_START, make_market_snapshot, provenance


def _legacy_090_payload(t: datetime) -> dict[str, object]:
    return {
        "schema_version": "0.9.0",
        "instrument_id": "EURUSD",
        "snapshot_time": t.isoformat(),
        "source_timestamp": t.isoformat(),
        "quote": {"bid": "1.08000", "ask": "1.08005"},
        "source": "fixture-feed",
        "produced_at": t.isoformat(),
        "trace_id": None,
        "provenance": provenance(t).model_dump(mode="json"),
    }


def test_upgrade_single_hop_chain() -> None:
    payload = _legacy_090_payload(FIXED_START)
    upgraded = upgrade_payload("market.snapshot.created", payload)
    assert upgraded["schema_version"] == "1.0.0"
    assert upgraded["as_of"] == FIXED_START.isoformat()
    assert "snapshot_time" not in upgraded
    assert "quote" not in upgraded
    assert upgraded["bid"] == "1.08000"
    assert upgraded["ask"] == "1.08005"
    # The upgraded payload validates against the current contract.
    MarketSnapshot.model_validate(upgraded)


def test_upgrade_current_payload_is_unchanged() -> None:
    payload = make_market_snapshot(FIXED_START).canonical_dict()
    upgraded = upgrade_payload("market.snapshot.created", payload)
    assert upgraded == payload


def test_upgrade_missing_schema_version_rejected() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        upgrade_payload("market.snapshot.created", {"bid": "1"})


def test_upgrade_without_path_raises() -> None:
    payload = _legacy_090_payload(FIXED_START)
    payload["schema_version"] = "0.0.1"
    with pytest.raises(UpgradeNotFoundError):
        upgrade_payload("market.snapshot.created", payload)


def test_deserialize_event_upgrades_legacy_payload() -> None:
    clock = VirtualClock(FIXED_START)
    envelope = {
        "schema_version": "1.0.0",
        "event_id": str(uuid4()),
        "trace_id": str(UUID(int=7)),
        "event_time": FIXED_START.isoformat(),
        "ingested_at": FIXED_START.isoformat(),
        "producer": "market-data",
        "event_name": "market.snapshot.created",
        "payload": _legacy_090_payload(FIXED_START),
        "provenance": {},
    }
    event = deserialize_event(envelope)
    assert event.payload["schema_version"] == "1.0.0"
    # model_validate_json re-serializes UTC as 'Z' (Pydantic v2 JSON mode).
    assert event.payload["as_of"] == FIXED_START.isoformat().replace("+00:00", "Z")
    assert clock.now() == FIXED_START
