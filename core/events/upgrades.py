"""Payload schema evolution (event versioning).

Payloads travel with their own ``schema_version``. When a contract changes, the new
payload version is registered and old payloads are upgraded through a linear chain of
registered :class:`PayloadUpgrader` functions before validation against the current
contract class.

Phase 0 ships one real example: ``market.snapshot.created`` v0.9.0 → v0.10.0 → v1.0.0.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.events.registry import CANONICAL_EVENT_REGISTRY
from core.schemas.base import DomainObject

__all__ = ["PayloadUpgrader", "UpgradeNotFoundError", "register_upgrade", "upgrade_payload"]

PayloadUpgrader = Callable[[dict[str, Any]], dict[str, Any]]

#: (event_name, from_version, to_version) → upgrade function.
_PAYLOAD_UPGRADES: dict[tuple[str, str, str], PayloadUpgrader] = {}


class UpgradeNotFoundError(ValueError):
    def __init__(self, event_name: str, from_version: str, to_version: str) -> None:
        super().__init__(f"no upgrade path for {event_name!r}: {from_version} -> {to_version}")
        self.event_name = event_name
        self.from_version = from_version
        self.to_version = to_version


def register_upgrade(
    event_name: str, from_version: str, to_version: str, upgrader: PayloadUpgrader
) -> None:
    key = (event_name, from_version, to_version)
    if key in _PAYLOAD_UPGRADES:
        raise ValueError(f"upgrade already registered for {key!r}")
    _PAYLOAD_UPGRADES[key] = upgrader


def _upgrade_chain(event_name: str, from_version: str, to_version: str) -> list[PayloadUpgrader]:
    """Resolve the linear chain from_version → … → to_version (empty when equal)."""
    chain: list[PayloadUpgrader] = []
    current = from_version
    seen: set[str] = set()
    while current != to_version:
        if current in seen:
            raise UpgradeNotFoundError(event_name, from_version, to_version)
        seen.add(current)
        hops = [
            (nxt, upgrader)
            for (name, frm, nxt), upgrader in _PAYLOAD_UPGRADES.items()
            if name == event_name and frm == current
        ]
        if not hops:
            raise UpgradeNotFoundError(event_name, from_version, to_version)
        if len(hops) > 1:
            raise ValueError(f"ambiguous upgrade path for {event_name!r} at {current}")
        next_version, upgrader = hops[0]
        chain.append(upgrader)
        current = next_version
    return chain


def upgrade_payload(event_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Upgrade ``payload`` to the schema version of its registered contract.

    Returns the payload unchanged when it is already current.
    """
    try:
        current_version = str(payload["schema_version"])
    except KeyError:
        raise ValueError(f"payload for {event_name!r} lacks schema_version") from None

    schema_cls: type[DomainObject] = CANONICAL_EVENT_REGISTRY.payload_schema(event_name)
    target_version = schema_cls.SCHEMA_VERSION

    result = dict(payload)
    for upgrader in _upgrade_chain(event_name, current_version, target_version):
        result = upgrader(result)
    result["schema_version"] = target_version
    return result


# ---------------------------------------------------------------------------
# Real example upgrade chain: market.snapshot.created 0.9.0 → 0.10.0 → 1.0.0
# ---------------------------------------------------------------------------


def _market_snapshot_090_to_0100(payload: dict[str, Any]) -> dict[str, Any]:
    """v0.9.0: rename snapshot_time → as_of (also rename its nested provenance)."""
    result = dict(payload)
    result["as_of"] = result.pop("snapshot_time")
    return result


def _market_snapshot_0100_to_100(payload: dict[str, Any]) -> dict[str, Any]:
    """v0.10.0: split the nested ``quote`` mapping into top-level bid/ask."""
    result = dict(payload)
    quote = result.pop("quote")
    result["bid"] = quote["bid"]
    result["ask"] = quote["ask"]
    return result


register_upgrade("market.snapshot.created", "0.9.0", "0.10.0", _market_snapshot_090_to_0100)
register_upgrade("market.snapshot.created", "0.10.0", "1.0.0", _market_snapshot_0100_to_100)
