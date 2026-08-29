"""Deterministic serialization tests for every canonical contract."""

from __future__ import annotations

from datetime import datetime

import pytest
from core.schemas import CANONICAL_CONTRACTS

from factories import FACTORY_BY_NAME


@pytest.mark.parametrize("name", sorted(CANONICAL_CONTRACTS))
def test_round_trip_is_lossless(name: str, fixed_start: datetime) -> None:
    obj = FACTORY_BY_NAME[name](fixed_start)
    raw = obj.to_json() if hasattr(obj, "to_json") else obj.model_dump_json()
    restored = type(obj).model_validate_json(raw)
    assert restored.model_dump(mode="json") == obj.model_dump(mode="json")


@pytest.mark.parametrize("name", sorted(CANONICAL_CONTRACTS))
def test_serialization_is_deterministic(name: str, fixed_start: datetime) -> None:
    """Same content -> same bytes, independent of construction time."""
    obj = FACTORY_BY_NAME[name](fixed_start)
    data = obj.model_dump(mode="json")
    again = type(obj).model_validate(data)
    assert again.model_dump(mode="json") == data
    assert again.model_dump_json() == obj.model_dump_json()


def test_json_uses_utc_iso_timestamps(fixed_start: datetime) -> None:
    from factories import make_market_snapshot

    snapshot = make_market_snapshot(fixed_start)
    payload = snapshot.canonical_dict()
    assert payload["as_of"].endswith("+00:00") or payload["as_of"].endswith("Z")
    assert isinstance(payload["bid"], str)  # Decimal serializes as string
