"""Temporal memory contract: ``MemoryEpisode`` (Graphiti, Phase 3+; INV-3, INV-11)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Self
from uuid import UUID

from pydantic import Field, model_validator

from core.domain.enums import MemoryLayer
from core.schemas.base import BaseContractModel, DomainObject, UtcDateTime, ensure_utc

__all__ = ["EntityRef", "MemoryEpisode", "RelationRef"]


class EntityRef(BaseContractModel):
    """Reference to an ontology entity (architecture §9: Instrument, Thesis, Signal…)."""

    entity_id: str = Field(min_length=1)
    entity_type: str = Field(min_length=1)
    name: str = Field(min_length=1)


class RelationRef(BaseContractModel):
    """Ontology relation between entity ids, e.g. SUPPORTS / CONTRADICTS."""

    source: str = Field(min_length=1)
    relation: str = Field(min_length=1)
    target: str = Field(min_length=1)


class MemoryEpisode(DomainObject):
    """One temporal memory episode with point-in-time validity (INV-3).

    A backtest at time T must never retrieve an episode whose ``valid_from`` is
    later than T — retrieval honors ``as_of`` via :meth:`is_valid_at`.
    """

    episode_id: UUID
    layer: MemoryLayer
    valid_from: UtcDateTime
    valid_until: UtcDateTime | None = None
    summary: str = Field(min_length=1)
    entities: list[EntityRef] = Field(default_factory=list)
    relations: list[RelationRef] = Field(default_factory=list)
    importance: float = Field(default=0.5, ge=0, le=1)
    source_trace_id: UUID | None = None
    embedding_ref: str | None = None
    content: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_validity(self) -> Self:
        if self.valid_until is not None and self.valid_until < self.valid_from:
            raise ValueError("valid_until must be >= valid_from")
        return self

    def is_valid_at(self, moment: datetime) -> bool:
        """True when the episode is observable at ``moment`` (point-in-time)."""
        moment_utc = ensure_utc(moment)
        if moment_utc < self.valid_from:
            return False
        return self.valid_until is None or moment_utc <= self.valid_until
