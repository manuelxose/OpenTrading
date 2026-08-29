"""Signal producers for the research stage (Phase 7).

- :class:`BaselineQuantProducer` — deterministic momentum signal implementing
  the canonical :class:`QuantSignal` interface (no ML yet; the Quant Factory is
  Phase 9). Pure function of the snapshot.
- :class:`MemoryContextProducer` — deterministic distillation of point-in-time
  Graphiti episodes into a :class:`MemoryContext` stance (INV-3, INV-11).

Both are advisory: they never order, never size (INV-1).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid5

from core.domain.enums import SignalDirection
from core.schemas import MemoryContext, QuantSignal
from core.schemas.base import Provenance
from core.schemas.market import MarketSnapshot
from core.schemas.research import EvidenceRef

__all__ = ["BaselineQuantProducer", "MemoryContextProducer"]

_PRODUCER = "apps.worker.producers"

_QUANT_NS = UUID("7c1d0f1e-2a3b-4c5d-8e9f-0a1b2c3d4e5f")

#: Content keys the pipeline's own episode writers use (see posttrade stage).
_STANCE_KEYS = ("stance", "direction")


def _signed_direction(value: float) -> SignalDirection:
    if value > 0:
        return SignalDirection.LONG
    if value < 0:
        return SignalDirection.SHORT
    return SignalDirection.FLAT


class BaselineQuantProducer:
    """Deterministic momentum quant signal from a single snapshot.

    ``strength`` scales the bar's open→close move by the bar range; with a
    degenerate range it falls back to a relative move vs the mid. Always
    reproducible from the snapshot alone.
    """

    def __init__(self, *, model_id: str, model_version: str) -> None:
        self._model_id = model_id
        self._model_version = model_version

    def produce(
        self,
        instrument_id: str,
        snapshot: MarketSnapshot,
        *,
        trace_id: UUID | None,
        produced_at: datetime,
    ) -> QuantSignal:
        mid = float(snapshot.mid)
        open_ = float(snapshot.open) if snapshot.open is not None else mid
        close = float(snapshot.close) if snapshot.close is not None else mid
        high = float(snapshot.high) if snapshot.high is not None else max(open_, close)
        low = float(snapshot.low) if snapshot.low is not None else min(open_, close)

        momentum = close - open_
        bar_range = high - low
        if bar_range > 0:
            strength = min(1.0, abs(momentum) / max(bar_range, mid * 0.0001))
            confidence = 0.5 + 0.5 * min(1.0, bar_range / max(mid * 0.0005, 1e-12))
        else:
            strength = min(1.0, abs(momentum) / max(mid * 0.001, 1e-12))
            confidence = 0.5
        direction = _signed_direction(momentum)

        return QuantSignal(
            signal_id=uuid5(_QUANT_NS, f"{instrument_id}:{snapshot.as_of.isoformat()}"),
            instrument_id=instrument_id,
            direction=direction,
            strength=round(strength, 6),
            confidence=round(confidence, 6),
            horizon_seconds=None,
            expected_return=round(momentum / mid, 6) if mid > 0 else 0.0,
            model_id=self._model_id,
            model_version=self._model_version,
            as_of=snapshot.as_of,
            trace_id=trace_id,
            produced_at=produced_at,
            provenance=Provenance(producer=_PRODUCER, produced_at=produced_at),
        )


class MemoryContextProducer:
    """Distills point-in-time memory episodes into a directional stance.

    Only episodes with a ``content.stance`` (written by the platform's own
    posttrade stage) vote; the stance is the importance-weighted sign of those
    votes. No episodes → ``None`` (fusion applies its missing-signal policy).
    """

    def __init__(self, *, memory: object, version: str, source: str, query_template: str) -> None:
        self._memory = memory
        self._version = version
        self._source = source
        self._template = query_template

    def produce(
        self,
        instrument_id: str,
        *,
        as_of: datetime,
        trace_id: UUID | None,
        produced_at: datetime,
    ) -> MemoryContext | None:
        memory = self._memory
        query = self._template.format(instrument=instrument_id)
        episodes = memory.search(  # type: ignore[attr-defined]
            query, as_of=as_of, limit=10, trace_id=trace_id
        )

        weighted = 0.0
        total_weight = 0.0
        confidence_sum = 0.0
        refs: list[EvidenceRef] = []
        for episode in episodes:
            stance = _episode_stance(episode)
            if stance is None:
                continue
            weight = float(episode.importance)
            sign = 1.0 if stance is SignalDirection.LONG else -1.0
            weighted += sign * weight
            total_weight += weight
            confidence_sum += weight * float(episode.importance)
            refs.append(
                EvidenceRef(
                    ref_id=str(episode.episode_id),
                    kind="episode",
                    source=self._source,
                    valid_at=as_of,
                    summary=episode.summary[:200],
                )
            )
        if total_weight == 0:
            return None
        direction = _signed_direction(weighted)
        score = min(1.0, abs(weighted) / total_weight)
        confidence = min(1.0, confidence_sum / total_weight) if refs else 0.0
        return MemoryContext(
            direction=direction,
            score=round(score, 6),
            confidence=round(confidence, 6),
            evidence_refs=refs,
            summary=f"memory stance over {len(refs)} episode(s)",
            memory_version=self._version,
            source=self._source,
            as_of=as_of,
        )


def _episode_stance(episode: object) -> SignalDirection | None:
    content = getattr(episode, "content", {}) or {}
    for key in _STANCE_KEYS:
        raw = content.get(key)
        if raw is None:
            continue
        try:
            return SignalDirection(str(raw).upper())
        except ValueError:
            return None
    return None
