"""Conceptual memory tiers as policies — not separate databases (ADR-0008, §11).

Graphiti physically implements the three FinMem-inspired layers. Here the tiers
are *metadata / relevance / temporal policies* applied over one single store:

- :meth:`TierPolicy.classify` — derives the tier of a record from its metadata
  (validity span, importance, entity types, relations), never from storage
  location;
- :meth:`TierPolicy.relevance` — exponential decay by knowledge age, with a
  half-life per tier (long-term structural lessons do not decay);
- :meth:`TierPolicy.reachable` — temporal reach: short-term knowledge stops
  being surfaced after days, medium-term after a year, long-term is always
  reachable (subject to the point-in-time filter).

The producer-declared ``MemoryEpisode.layer`` is advisory only: the policy is
authoritative and deterministic, which keeps historical simulations reproducible.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

from core.domain.enums import MemoryLayer
from core.schemas.base import ensure_utc

from adapters.graphiti.errors import LayerPolicyError
from adapters.graphiti.ontology import EntityType, RelationType
from adapters.graphiti.schemas import MemoryRecord

__all__ = ["TierPolicy"]

#: Entity types that make a record structural (candidates for long-term memory).
_LONG_ENTITY_HINTS = frozenset(
    {
        EntityType.THESIS.value,
        EntityType.STRATEGY.value,
        EntityType.FACTOR.value,
        EntityType.MODEL.value,
        EntityType.EXPERIMENT.value,
    }
)

#: Relations that encode durable lessons (postmortem semantics, §11 long-term).
_LONG_RELATION_HINTS = frozenset(
    {RelationType.LEARNED_FROM.value, RelationType.FAILED_IN_REGIME.value}
)

#: Entity types that encode fast-moving facts (hours/days horizon).
_SHORT_ENTITY_HINTS = frozenset(
    {
        EntityType.MACRO_EVENT.value,
        EntityType.NEWS_EVENT.value,
        EntityType.RISK_EVENT.value,
        EntityType.SIGNAL.value,
        EntityType.TRADE.value,
    }
)


class TierPolicy:
    """Deterministic tier classification, relevance decay and reach windows."""

    SHORT_SPAN_MAX: timedelta = timedelta(days=14)
    MEDIUM_SPAN_MAX: timedelta = timedelta(days=365)
    SHORT_HALF_LIFE: timedelta = timedelta(days=3)
    MEDIUM_HALF_LIFE: timedelta = timedelta(days=45)
    SHORT_REACH: timedelta = timedelta(days=14)
    MEDIUM_REACH: timedelta = timedelta(days=365)
    LONG_IMPORTANCE_THRESHOLD: float = 0.7

    def __init__(
        self,
        *,
        short_span_max: timedelta | None = None,
        medium_span_max: timedelta | None = None,
        short_half_life: timedelta | None = None,
        medium_half_life: timedelta | None = None,
        short_reach: timedelta | None = None,
        medium_reach: timedelta | None = None,
        long_importance_threshold: float | None = None,
    ) -> None:
        self.short_span_max = short_span_max if short_span_max is not None else self.SHORT_SPAN_MAX
        self.medium_span_max = (
            medium_span_max if medium_span_max is not None else self.MEDIUM_SPAN_MAX
        )
        self.short_half_life = (
            short_half_life if short_half_life is not None else self.SHORT_HALF_LIFE
        )
        self.medium_half_life = (
            medium_half_life if medium_half_life is not None else self.MEDIUM_HALF_LIFE
        )
        self.short_reach = short_reach if short_reach is not None else self.SHORT_REACH
        self.medium_reach = medium_reach if medium_reach is not None else self.MEDIUM_REACH
        self.long_importance_threshold = (
            long_importance_threshold
            if long_importance_threshold is not None
            else self.LONG_IMPORTANCE_THRESHOLD
        )
        self._validate()

    def _validate(self) -> None:
        if self.short_span_max >= self.medium_span_max:
            raise LayerPolicyError("short_span_max must be smaller than medium_span_max")
        if self.short_reach >= self.medium_reach:
            raise LayerPolicyError("short_reach must be smaller than medium_reach")
        if self.short_half_life <= timedelta(0) or self.medium_half_life <= timedelta(0):
            raise LayerPolicyError("half-lives must be positive")
        if not 0.0 <= self.long_importance_threshold <= 1.0:
            raise LayerPolicyError("long_importance_threshold must be within [0, 1]")

    # ── classification ────────────────────────────────────────────────────

    @staticmethod
    def _has_structural_hint(record: MemoryRecord) -> bool:
        if any(e.entity_type in _LONG_ENTITY_HINTS for e in record.entities):
            return True
        return any(r.relation in _LONG_RELATION_HINTS for r in record.relations)

    @staticmethod
    def _has_short_hint(record: MemoryRecord) -> bool:
        return any(e.entity_type in _SHORT_ENTITY_HINTS for e in record.entities)

    def classify(self, record: MemoryRecord) -> MemoryLayer:
        """Derive the tier from metadata only: validity span, importance, hints.

        - open-ended validity or spans >= medium_span_max → long-term;
        - structural entities/relations with importance >= threshold → long-term;
        - spans <= short_span_max with short-horizon hints or low importance →
          short-term;
        - everything else → medium-term.
        """
        span = record.validity.span()
        if span is None or span >= self.medium_span_max.total_seconds():
            return MemoryLayer.LONG_TERM
        if self._has_structural_hint(record) and (
            record.importance >= self.long_importance_threshold
        ):
            return MemoryLayer.LONG_TERM
        if span <= self.short_span_max.total_seconds() and (
            self._has_short_hint(record) or record.importance < 0.6
        ):
            return MemoryLayer.SHORT_TERM
        return MemoryLayer.MEDIUM_TERM

    # ── relevance ─────────────────────────────────────────────────────────

    def half_life(self, layer: MemoryLayer) -> timedelta | None:
        """Decay half-life per tier; long-term knowledge does not decay."""
        if layer is MemoryLayer.SHORT_TERM:
            return self.short_half_life
        if layer is MemoryLayer.MEDIUM_TERM:
            return self.medium_half_life
        return None

    def relevance(self, record: MemoryRecord, at: datetime) -> float:
        """Relevance multiplier in [0, 1] for knowledge of age ``at - available_time``."""
        moment = ensure_utc(at)
        layer = self.classify(record)
        half_life = self.half_life(layer)
        if half_life is None:
            return 1.0
        age = (moment - record.available_time).total_seconds()
        if age < 0:
            return 0.0
        # 0.5 ** (age / half_life) expressed via exp for exact float typing.
        return math.exp((age / half_life.total_seconds()) * math.log(0.5))

    # ── reach ─────────────────────────────────────────────────────────────

    def reachable(self, record: MemoryRecord, at: datetime) -> bool:
        """Whether the tier policy still surfaces this record at ``at``.

        Long-term (structural) memory is always reachable; short-term and
        medium-term knowledge age out of the reach window. The point-in-time
        filter runs first, so ``at >= available_time`` is guaranteed here.
        """
        moment = ensure_utc(at)
        age = moment - record.available_time
        layer = self.classify(record)
        if layer is MemoryLayer.LONG_TERM:
            return True
        if layer is MemoryLayer.SHORT_TERM:
            return age <= self.short_reach
        return age <= self.medium_reach
