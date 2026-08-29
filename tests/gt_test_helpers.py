"""Test helpers for the graphiti adapter (mirrors ta_test_helpers.py)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from adapters.graphiti.schemas import MemoryRecord
from core.clock.clocks import VirtualClock
from core.schemas.memory import MemoryEpisode

from factories import FIXED_START, make_memory_episode

__all__ = [
    "FakeEdge",
    "FakeGraph",
    "build_memory",
    "make_record",
    "window_blind_store",
]


def make_record(
    t: datetime,
    *,
    source: str = "tests.graphiti.helpers",
    event_time: datetime | None = None,
    available_time: datetime | None = None,
    ingested_at: datetime | None = None,
    episode: MemoryEpisode | None = None,
    **overrides: Any,
) -> MemoryRecord:
    """One stored record with a coherent temporal envelope around ``t``."""
    return MemoryRecord.from_episode(
        episode or make_memory_episode(t),
        source=source,
        event_time=event_time or t - timedelta(hours=2),
        available_time=available_time or t - timedelta(hours=1),
        ingested_at=ingested_at or t,
    ).model_copy(update=overrides or None)


def build_memory(*records: MemoryRecord, start: datetime = FIXED_START) -> Any:
    """A ready-to-query :class:`adapters.graphiti.memory.Memory` over the
    in-memory twin, with a virtual clock at ``start``. Stored tiers are derived
    by the default policy — the same step ``Memory.ingest`` performs."""
    from adapters.graphiti import InMemoryStore, Memory, TierPolicy

    policy = TierPolicy()
    stored = (record.model_copy(update={"layer": policy.classify(record)}) for record in records)
    return Memory(InMemoryStore(stored), clock=VirtualClock(start))


class _WindowBlindStore:
    """Deliberately broken backend: ignores the temporal window and returns
    every record (used to prove the repository's authoritative filter)."""

    def __init__(self, records: tuple[MemoryRecord, ...] = ()) -> None:
        self._records: dict[UUID, MemoryRecord] = {r.episode_id: r for r in records}

    def store(self, record: MemoryRecord) -> None:
        self._records[record.episode_id] = record

    def search(self, query: str, window: Any) -> tuple[Any, ...]:
        from adapters.graphiti.schemas import MemoryHit

        return tuple(MemoryHit(record=r, score=1.0) for r in self._records.values())

    def close(self) -> None:
        pass


def window_blind_store(*records: MemoryRecord) -> _WindowBlindStore:
    """A backend that leaks everything — for defense-in-depth tests."""
    return _WindowBlindStore(tuple(records))


class FakeGraph:
    """Upstream graph double: records add_episode calls, returns queued edges."""

    def __init__(self) -> None:
        self.added: list[dict[str, Any]] = []
        self.search_results: list[Any] = []
        self.closed = False

    def add_episode(self, **kwargs: Any) -> None:
        self.added.append(dict(kwargs))

    def search(self, query: str, num_results: int = 10, search_filter: Any = None) -> list[Any]:
        return list(self.search_results)

    def close(self) -> None:
        self.closed = True


class FakeEdge:
    """Minimal upstream EntityEdge double carrying episode uuids."""

    def __init__(self, episodes: list[str]) -> None:
        self.episodes = episodes


class FakeUpstream:
    """Upstream module double returned by the lazy import seam."""

    def __init__(self) -> None:
        self.graph = FakeGraph()
        self.driver_kwargs: dict[str, Any] = {}
        self.filter_kwargs: dict[str, Any] = {}

    def __call__(self) -> tuple[Any, ...]:
        captured = self

        class _GraphCls:
            def __new__(cls, **kwargs: Any) -> FakeGraph:
                return captured.graph

        class _FalkorCls:
            def __new__(cls, **kwargs: Any) -> _FalkorCls:
                captured.driver_kwargs.update(kwargs)
                return super().__new__(cls)

            def __init__(self, **kwargs: Any) -> None:
                pass

        class _FiltersCls:
            def __new__(cls, **kwargs: Any) -> _FiltersCls:
                captured.filter_kwargs.update(kwargs)
                return super().__new__(cls)

            def __init__(self, **kwargs: Any) -> None:
                pass

        class _DateCls:
            def __new__(cls, **kwargs: Any) -> _DateCls:
                instance = super().__new__(cls)
                instance.__dict__.update(kwargs)
                return instance

            def __init__(self, **kwargs: Any) -> None:
                pass

        class _EpisodeType:
            text = "text"

        return _GraphCls, _FalkorCls, _FiltersCls, _DateCls, _EpisodeType
