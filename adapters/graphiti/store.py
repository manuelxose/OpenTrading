"""Backend seam for temporal memory (ADR-0008).

- :class:`MemoryStore` — the protocol every backend implements
  (live Graphiti-over-FalkorDB, or the deterministic in-memory twin for tests);
- :class:`InMemoryStore` — the in-memory twin. It honors the same temporal
  window pushdown as the live store, but it is **never** the authoritative
  point-in-time filter: :class:`adapters.graphiti.memory.PointInTimeFilter`
  re-checks every hit after the backend returns.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol
from uuid import UUID

from adapters.graphiti.schemas import MemoryHit, MemoryRecord, SearchWindow

__all__ = ["InMemoryStore", "MemoryStore"]


class MemoryStore(Protocol):
    """Storage protocol: write records, search within a temporal window."""

    def store(self, record: MemoryRecord) -> None:
        """Persist one memory record (idempotent per ``episode_id``)."""
        ...

    def search(self, query: str, window: SearchWindow) -> tuple[MemoryHit, ...]:
        """Return hits matching ``query`` within the pushed-down temporal window.

        The window is an optimization only; the repository re-verifies point-in-time
        observability of every hit.
        """
        ...

    def close(self) -> None:
        """Release backend resources (no-op for in-memory)."""
        ...


def _tokens(text: str) -> frozenset[str]:
    return frozenset(word for word in text.lower().replace("_", " ").split() if len(word) > 1)


class InMemoryStore:
    """Deterministic in-memory backend — same window semantics as the live store.

    Scoring stands in for Graphiti's hybrid (vector + BM25 + graph) search:
    lexical overlap against summary/entity names blended with importance. It is
    deterministic so historical queries are reproducible.
    """

    def __init__(self, records: Iterable[MemoryRecord] = ()) -> None:
        if isinstance(records, MemoryRecord):  # single-record convenience
            records = (records,)
        self._records: dict[UUID, MemoryRecord] = {}
        for record in records:
            self.store(record)

    # ── MemoryStore protocol ──────────────────────────────────────────────

    def store(self, record: MemoryRecord) -> None:
        """Idempotent write keyed by ``episode_id`` (replays overwrite safely)."""
        self._records[record.episode_id] = record

    def search(self, query: str, window: SearchWindow) -> tuple[MemoryHit, ...]:
        query_tokens = _tokens(query)
        scored: list[MemoryHit] = []
        for record in self._records.values():
            if not self._in_window(record, window):
                continue
            scored.append(MemoryHit(record=record, score=self._score(record, query_tokens)))
        scored.sort(key=lambda hit: (-hit.score, str(hit.record.episode_id)))
        return tuple(scored[: window.limit])

    def close(self) -> None:
        """Nothing to release."""

    # ── internals ─────────────────────────────────────────────────────────

    @staticmethod
    def _in_window(record: MemoryRecord, window: SearchWindow) -> bool:
        if record.available_time > window.as_of:
            return False
        if not record.validity.contains(window.as_of):
            return False
        if window.layers is not None and record.layer not in window.layers:
            return False
        return record.importance >= window.min_importance

    @staticmethod
    def _score(record: MemoryRecord, query_tokens: frozenset[str]) -> float:
        if not query_tokens:
            return float(record.importance)
        haystack = " ".join(
            [record.summary]
            + [e.name for e in record.entities]
            + [e.entity_id for e in record.entities]
        )
        haystack_tokens = _tokens(haystack)
        overlap = len(query_tokens & haystack_tokens) / len(query_tokens)
        return round(0.6 * overlap + 0.4 * record.importance, 6)

    #: All stored records (test/debug surface; not part of the search path).
    def all_records(self) -> tuple[MemoryRecord, ...]:
        return tuple(self._records.values())
