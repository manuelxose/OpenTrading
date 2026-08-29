"""Storage envelope for temporal memory (ADR-0008, INV-3).

Every stored memory item preserves the full point-in-time envelope:

- ``source`` — which upstream component produced the knowledge;
- ``event_time`` — when the underlying event happened;
- ``available_time`` — when the system could first have known about it
  (the single fact that decides observability at time T);
- ``ingested_at`` — when the item was actually written into memory;
- ``validity`` — the [valid_from, valid_until] interval in which the claim holds;
- ``trace_id`` — end-to-end correlation id;
- ``provenance`` — producer, code version, upstream source ids.

Temporal ordering is enforced at construction: an event cannot be known before it
happens (``event_time <= available_time``) and cannot be ingested before it is
available (``available_time <= ingested_at``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Self
from uuid import UUID

from core.domain.enums import MemoryLayer
from core.schemas.base import BaseContractModel, Provenance, UtcDateTime, ensure_utc
from core.schemas.memory import EntityRef, MemoryEpisode, RelationRef
from pydantic import Field, model_validator

from adapters.graphiti.errors import TemporalOrderingError

__all__ = ["GraphitiConfig", "MemoryHit", "MemoryRecord", "SearchWindow", "Validity"]


class Validity(BaseContractModel):
    """Temporal validity interval [``valid_from``, ``valid_until``].

    ``valid_until=None`` means "open-ended" (long-term structural lessons).
    """

    valid_from: UtcDateTime
    valid_until: UtcDateTime | None = None

    @model_validator(mode="after")
    def _check_interval(self) -> Self:
        if self.valid_until is not None and self.valid_until < self.valid_from:
            raise ValueError("valid_until must be >= valid_from")
        return self

    def contains(self, moment: datetime) -> bool:
        moment_utc = ensure_utc(moment)
        if moment_utc < self.valid_from:
            return False
        return self.valid_until is None or moment_utc <= self.valid_until

    def span(self) -> float | None:
        """Duration in seconds, or None when open-ended."""
        if self.valid_until is None:
            return None
        return (self.valid_until - self.valid_from).total_seconds()


class MemoryRecord(BaseContractModel):
    """One stored memory item: the ontology content plus the temporal envelope."""

    episode_id: UUID
    layer: MemoryLayer
    summary: str = Field(min_length=1)
    entities: tuple[EntityRef, ...] = Field(default_factory=tuple)
    relations: tuple[RelationRef, ...] = Field(default_factory=tuple)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    content: dict[str, Any] = Field(default_factory=dict)

    # Temporal envelope (INV-3) — see module docstring for semantics.
    source: str = Field(min_length=1)
    event_time: UtcDateTime
    available_time: UtcDateTime
    ingested_at: UtcDateTime
    validity: Validity

    trace_id: UUID | None = None
    provenance: Provenance

    @model_validator(mode="after")
    def _check_temporal_order(self) -> Self:
        if self.event_time > self.available_time:
            raise TemporalOrderingError(
                f"episode {self.episode_id}: event_time {self.event_time.isoformat()} "
                f"is after available_time {self.available_time.isoformat()}"
            )
        if self.available_time > self.ingested_at:
            raise TemporalOrderingError(
                f"episode {self.episode_id}: available_time {self.available_time.isoformat()} "
                f"is after ingested_at {self.ingested_at.isoformat()}"
            )
        return self

    def observable_at(self, moment: datetime) -> bool:
        """Point-in-time truth: the system could know this item at ``moment``
        only if it was already available and still valid."""
        moment_utc = ensure_utc(moment)
        return self.available_time <= moment_utc and self.validity.contains(moment_utc)

    @classmethod
    def from_episode(
        cls,
        episode: MemoryEpisode,
        *,
        source: str,
        event_time: datetime,
        available_time: datetime,
        ingested_at: datetime,
    ) -> MemoryRecord:
        """Map a domain :class:`MemoryEpisode` to the stored envelope.

        ``source`` / ``event_time`` / ``available_time`` are supplied by the
        ingesting component; ``ingested_at`` comes from the memory clock.
        """
        return cls(
            episode_id=episode.episode_id,
            layer=episode.layer,
            summary=episode.summary,
            entities=tuple(episode.entities),
            relations=tuple(episode.relations),
            importance=episode.importance,
            content=dict(episode.content),
            source=source,
            event_time=ensure_utc(event_time),
            available_time=ensure_utc(available_time),
            ingested_at=ensure_utc(ingested_at),
            validity=Validity(
                valid_from=ensure_utc(episode.valid_from),
                valid_until=(
                    ensure_utc(episode.valid_until) if episode.valid_until is not None else None
                ),
            ),
            trace_id=episode.trace_id,
            provenance=episode.provenance,
        )

    def to_episode(self) -> MemoryEpisode:
        """Map the stored record back to the domain contract."""
        return MemoryEpisode(
            episode_id=self.episode_id,
            layer=self.layer,
            valid_from=self.validity.valid_from,
            valid_until=self.validity.valid_until,
            summary=self.summary,
            entities=list(self.entities),
            relations=list(self.relations),
            importance=self.importance,
            source_trace_id=self.trace_id,
            content=dict(self.content),
            produced_at=self.ingested_at,
            trace_id=self.trace_id,
            provenance=self.provenance,
        )


class SearchWindow(BaseContractModel):
    """Temporal window pushed down to the store as an optimization.

    The authoritative point-in-time filter lives in the repository
    (:class:`adapters.graphiti.memory.PointInTimeFilter`) and re-checks every
    hit — the window is never trusted alone.
    """

    as_of: UtcDateTime
    layers: tuple[MemoryLayer, ...] | None = None
    min_importance: float = Field(default=0.0, ge=0.0, le=1.0)
    limit: int = Field(default=10, ge=1)

    @model_validator(mode="after")
    def _check_layers(self) -> Self:
        if self.layers is not None and not self.layers:
            raise ValueError("layers must be None or a non-empty tuple")
        return self


class MemoryHit(BaseContractModel):
    """One store search result: the full record plus a relevance score."""

    record: MemoryRecord
    score: float = Field(default=1.0, ge=0.0)


class GraphitiConfig(BaseContractModel):
    """Connection settings for the live Graphiti-over-FalkorDB store."""

    host: str = "127.0.0.1"
    port: int = Field(default=6380, ge=1, le=65535)
    username: str | None = None
    password: str | None = None
    database: str = Field(default="default_db", min_length=1)
