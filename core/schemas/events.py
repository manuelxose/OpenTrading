"""Standard event envelope: ``DomainEvent`` (architecture §14, INV-15).

Envelope fields: ``schema_version``, ``event_id``, ``trace_id``, ``event_time``,
``ingested_at``, ``producer``, ``payload``, ``provenance`` — plus ``event_name``
(routing key; documented in docs/architecture/PHASE0_FOUNDATIONS.md).
"""

from __future__ import annotations

from typing import Any, ClassVar, Self
from uuid import UUID

from pydantic import Field, model_validator

from core.schemas.base import BaseContractModel, UtcDateTime

__all__ = ["EVENT_ENVELOPE_SCHEMA_VERSION", "DomainEvent"]

EVENT_ENVELOPE_SCHEMA_VERSION = "1.0.0"


class DomainEvent(BaseContractModel):
    SCHEMA_VERSION: ClassVar[str] = EVENT_ENVELOPE_SCHEMA_VERSION

    schema_version: str = Field(default=EVENT_ENVELOPE_SCHEMA_VERSION)
    event_id: UUID
    trace_id: UUID | None = None
    event_time: UtcDateTime
    ingested_at: UtcDateTime
    producer: str = Field(min_length=1)
    event_name: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_envelope(self) -> Self:
        if self.schema_version != EVENT_ENVELOPE_SCHEMA_VERSION:
            raise ValueError(
                f"event envelope requires schema_version "
                f"{EVENT_ENVELOPE_SCHEMA_VERSION!r}, got {self.schema_version!r}"
            )
        if self.ingested_at < self.event_time:
            raise ValueError("ingested_at must be >= event_time")
        return self
