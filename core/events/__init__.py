"""Event layer: registry, payload versioning, standard envelope (INV-15)."""

from core.events.envelope import build_domain_event, deserialize_event, serialize_event
from core.events.registry import (
    CANONICAL_EVENT_PAYLOAD_SCHEMAS,
    CANONICAL_EVENT_REGISTRY,
    EventRegistry,
    UnknownEventError,
)
from core.events.upgrades import (
    PayloadUpgrader,
    UpgradeNotFoundError,
    register_upgrade,
    upgrade_payload,
)

__all__ = [
    "CANONICAL_EVENT_PAYLOAD_SCHEMAS",
    "CANONICAL_EVENT_REGISTRY",
    "EventRegistry",
    "PayloadUpgrader",
    "UnknownEventError",
    "UpgradeNotFoundError",
    "build_domain_event",
    "deserialize_event",
    "register_upgrade",
    "serialize_event",
    "upgrade_payload",
]
