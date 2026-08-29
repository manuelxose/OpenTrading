"""Research contracts: ``ResearchRequest`` and ``ResearchPacket``."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import Field

from core.domain.enums import ResearchStatus
from core.schemas.base import BaseContractModel, DomainObject, UtcDateTime

__all__ = ["EvidenceRef", "ResearchPacket", "ResearchRequest"]


class EvidenceRef(BaseContractModel):
    """Pointer to an evidence source (document, memory episode, dataset, artifact)."""

    ref_id: str = Field(min_length=1)
    kind: str = Field(min_length=1, description="document | episode | dataset | artifact")
    source: str = Field(min_length=1)
    valid_at: UtcDateTime | None = Field(
        default=None, description="Point-in-time validity of the referenced evidence"
    )
    summary: str | None = None


class ResearchRequest(DomainObject):
    """A research question submitted to the qualitative/quantitative pipeline."""

    request_id: UUID
    title: str = Field(min_length=1)
    question: str = Field(min_length=1)
    hypotheses: list[str] = Field(default_factory=list)
    scope: list[str] = Field(default_factory=list)
    requested_by: str = Field(min_length=1)
    priority: int = Field(default=3, ge=1, le=5)
    status: ResearchStatus = ResearchStatus.PENDING
    deadline: UtcDateTime | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class ResearchPacket(DomainObject):
    """Findings answering a :class:`ResearchRequest`, with cited evidence."""

    packet_id: UUID
    request_id: UUID
    summary: str = Field(min_length=1)
    findings: list[str] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0, le=1)
    authors: list[str] = Field(default_factory=list)
    related_instruments: list[str] = Field(default_factory=list)
