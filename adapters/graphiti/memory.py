"""Domain-facing temporal memory (ADR-0008, INV-3) — the only query path.

:class:`Memory` is what agents and backtests call:

    memory.search("regime behavior", as_of=simulation_clock.now())

It guarantees the Phase 3 Definition of Done: *an analysis at time T can query
what the system knew at T, without seeing what it learned after T.*

- :class:`PointInTimeFilter` is the single INV-3 choke point: no record with
  ``available_time > as_of`` (or outside its validity interval) may surface.
- The tier policy prunes short/medium-term knowledge that has aged out of reach
  and decays relevance — all in one store, never three databases.
- ``strict=True`` turns a store-side window violation into a raised
  :class:`FutureMemoryLeakageError` (defense in depth; the default silently
  drops).
"""

from __future__ import annotations

import time
from contextlib import nullcontext
from datetime import datetime
from uuid import UUID

from core.clock.clocks import Clock, SystemClock
from core.domain.enums import MemoryLayer
from core.observability.metrics import OperationalMetrics, metrics
from core.observability.tracing import LangfuseTracer, tracer
from core.schemas.base import ensure_utc
from core.schemas.memory import MemoryEpisode

from adapters.graphiti.errors import FutureMemoryLeakageError
from adapters.graphiti.ontology import validate_episode_refs
from adapters.graphiti.schemas import MemoryHit, MemoryRecord, SearchWindow
from adapters.graphiti.store import MemoryStore
from adapters.graphiti.tiers import TierPolicy

__all__ = ["Memory", "PointInTimeFilter"]


class PointInTimeFilter:
    """The single INV-3 choke point (mirrors the market data filter).

    Dropping logic in exactly one place makes the absolute invariant auditable:
    **no record with available_time > as_of may appear in a query result.**
    """

    def __init__(self, as_of: datetime) -> None:
        self._as_of = ensure_utc(as_of)

    @property
    def as_of(self) -> datetime:
        return self._as_of

    def keep(self, record: MemoryRecord) -> bool:
        return record.observable_at(self._as_of)

    def apply(self, hits: tuple[MemoryHit, ...] | list[MemoryHit]) -> tuple[MemoryHit, ...]:
        return tuple(hit for hit in hits if self.keep(hit.record))

    def dropped(self, hits: tuple[MemoryHit, ...] | list[MemoryHit]) -> tuple[MemoryHit, ...]:
        """The complement of :meth:`apply` — hits that violate point-in-time
        observability (used by defense-in-depth guards and the leakage suite)."""
        return tuple(hit for hit in hits if not self.keep(hit.record))


class Memory:
    """Temporal semantic memory: ingest episodes, search as-of a moment.

    The three conceptual tiers (short/medium/long-term) are policies applied by
    :class:`TierPolicy` over the single backend store — retrieval never fans out
    to three databases (ADR-0008, architecture §11).
    """

    def __init__(
        self,
        store: MemoryStore,
        *,
        policy: TierPolicy | None = None,
        clock: Clock | None = None,
        telemetry: LangfuseTracer | None = None,
        operational_metrics: OperationalMetrics | None = None,
    ) -> None:
        self._store = store
        self._policy = policy or TierPolicy()
        self._clock = clock or SystemClock()
        self._telemetry = telemetry or tracer
        self._metrics = operational_metrics or metrics

    @property
    def policy(self) -> TierPolicy:
        return self._policy

    def ingest(
        self,
        episode: MemoryEpisode,
        *,
        source: str,
        event_time: datetime,
        available_time: datetime,
        ingested_at: datetime | None = None,
    ) -> MemoryRecord:
        """Write one episode into memory.

        ``available_time`` is the moment the system could first know the fact —
        the caller (agent, feed adapter, postmortem importer) must state it
        explicitly; it is never inferred. ``ingested_at`` defaults to the memory
        clock. The stored tier is derived by the policy from metadata, so the
        producer-declared ``episode.layer`` is advisory only.
        """
        validate_episode_refs(episode.entities, episode.relations)
        record = MemoryRecord.from_episode(
            episode,
            source=source,
            event_time=event_time,
            available_time=available_time,
            ingested_at=ingested_at or self._clock.now(),
        )
        record = record.model_copy(update={"layer": self._policy.classify(record)})
        self._store.store(record)
        return record

    def search(
        self,
        query: str,
        *,
        as_of: datetime,
        layers: tuple[MemoryLayer, ...] | None = None,
        limit: int = 10,
        min_importance: float = 0.0,
        strict: bool = False,
        trace_id: UUID | None = None,
    ) -> tuple[MemoryEpisode, ...]:
        """Point-in-time retrieval: what the system knew at ``as_of``.

        Never exposes an episode whose ``available_time > as_of``, whose validity
        interval does not contain ``as_of``, or whose tier has aged out of reach.
        ``strict=True`` raises :class:`FutureMemoryLeakageError` if the backend
        window returns anything unobservable at ``as_of`` (defense in depth).
        """
        as_of_utc = ensure_utc(as_of)
        window = SearchWindow(
            as_of=as_of_utc,
            layers=layers,
            min_importance=min_importance,
            limit=max(limit, 1),
        )
        began = time.perf_counter()
        context = (
            self._telemetry.observation(
                trace_id=trace_id,
                name="graphiti.retrieve",
                as_type="retriever",
                metadata={"backend": "graphiti", "operation": "search"},
                input={"as_of": as_of_utc.isoformat(), "limit": limit},
            )
            if trace_id is not None
            else nullcontext(None)
        )
        try:
            with context as observation:
                hits = self._store.search(query, window)
                if observation is not None:
                    observation.update(output={"hits": len(hits)})
        except Exception:
            self._metrics.retrieval_duration.labels(backend="graphiti", status="error").observe(
                time.perf_counter() - began
            )
            raise
        self._metrics.retrieval_duration.labels(backend="graphiti", status="ok").observe(
            time.perf_counter() - began
        )
        self._metrics.retrieval_hits.labels(backend="graphiti").observe(len(hits))

        pit = PointInTimeFilter(as_of_utc)
        if strict:
            leaked = pit.dropped(hits)
            if leaked:
                bad = leaked[0].record
                raise FutureMemoryLeakageError(
                    f"backend returned episode {bad.episode_id} "
                    f"(available_time={bad.available_time.isoformat()}) for as_of "
                    f"{as_of_utc.isoformat()}"
                )
        hits = pit.apply(hits)

        reachable: list[MemoryHit] = [
            hit for hit in hits if self._policy.reachable(hit.record, as_of_utc)
        ]
        reachable.sort(
            key=lambda hit: (
                -hit.score * self._policy.relevance(hit.record, as_of_utc),
                str(hit.record.episode_id),
            )
        )
        return tuple(hit.record.to_episode() for hit in reachable[:limit])
