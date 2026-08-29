"""Shared bases for all canonical domain contracts.

Every canonical contract:

- carries ``schema_version`` pinned to its class constant ``SCHEMA_VERSION``;
- carries ``trace_id`` (nullable) for end-to-end reconstruction (architecture §31);
- carries ``produced_at`` — a timezone-aware UTC timestamp supplied by a
  :class:`core.clock.Clock` (no component may call ``datetime.now()`` directly);
- carries :class:`Provenance` metadata (producer, code version, source ids);
- is immutable (``frozen=True``) and closed to undeclared fields (``extra="forbid"``);
- serializes deterministically via :meth:`DomainObject.to_json` /
  :meth:`DomainObject.from_json` (Pydantic v2 JSON mode, field order fixed by class
  definition).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any, ClassVar, Self, TypeVar
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

#: Canonical schema version for every contract defined in Phase 0.
#: Bumping procedure: see docs/architecture/PHASE0_FOUNDATIONS.md §"Schema evolution".
SCHEMA_VERSION = "1.0.0"


def ensure_utc(value: datetime) -> datetime:
    """Normalize ``value`` to UTC; reject naive datetimes.

    Naive timestamps are ambiguous across timezones and break point-in-time
    guarantees (INV-3), so they are refused rather than silently assumed.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


#: Type alias enforcing timezone-aware UTC on every timestamp field.
UtcDateTime = Annotated[datetime, AfterValidator(ensure_utc)]


class BaseContractModel(BaseModel):
    """Common configuration shared by all contracts and sub-models."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    #: Schema version of this contract family. Subclasses bump it on change.
    SCHEMA_VERSION: ClassVar[str] = SCHEMA_VERSION


class Provenance(BaseContractModel):
    """Provenance metadata required on every canonical contract."""

    producer: str = Field(min_length=1, description="Component that created this object")
    produced_at: UtcDateTime
    code_version: str | None = Field(
        default=None, description="Version of the producing component's code"
    )
    source_ids: dict[str, str] = Field(
        default_factory=dict,
        description="Upstream object ids this object derives from (e.g. order_intent_id)",
    )
    notes: dict[str, str] = Field(default_factory=dict)


TSelf = TypeVar("TSelf", bound="DomainObject")


class DomainObject(BaseContractModel):
    """Base class for the canonical domain contracts (architecture §15)."""

    schema_version: str = Field(
        default=SCHEMA_VERSION,
        description="Schema version of this contract. Pinned to the class constant.",
    )
    trace_id: UUID | None = Field(
        default=None,
        description="End-to-end correlation id (architecture §31)",
    )
    produced_at: UtcDateTime
    provenance: Provenance

    @model_validator(mode="after")
    def _pin_schema_version(self) -> Self:
        if self.schema_version != self.SCHEMA_VERSION:
            raise ValueError(
                f"{type(self).__name__} requires schema_version "
                f"{self.SCHEMA_VERSION!r}, got {self.schema_version!r}"
            )
        return self

    def to_json(self) -> str:
        """Deterministic JSON serialization (UTF-8 stable, field order = definition order)."""
        return self.model_dump_json()

    def to_json_bytes(self) -> bytes:
        return self.to_json().encode("utf-8")

    @classmethod
    def from_json(cls: type[TSelf], raw: str | bytes | dict[str, Any]) -> TSelf:
        """Deserialize from JSON text, JSON bytes, or an already-decoded mapping."""
        if isinstance(raw, dict):
            return cls.model_validate(raw)
        return cls.model_validate_json(raw)

    def canonical_dict(self) -> dict[str, Any]:
        """JSON-mode mapping (UUIDs as str, Decimals as str) for payload embedding."""
        return self.model_dump(mode="json")
