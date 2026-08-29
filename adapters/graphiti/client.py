"""Live Graphiti-over-FalkorDB store — the ONLY module allowed to import upstream.

Boundary rules (ADR-0008, INV-11, INV-14):

- upstream ``graphiti_core`` is imported lazily inside :func:`_load_upstream`
  (never at module import time), so the package loads fine without Graphiti
  installed;
- the installed distribution version is checked against the pin in ``pin.py``;
- every upstream failure is translated into a typed
  :class:`~adapters.graphiti.errors.GraphitiError` — no upstream exception ever
  crosses this boundary;
- the graph's temporal edges are keyed to ``available_time`` (knowledge time),
  so Graphiti's own temporal filters align with the point-in-time invariant;
- search results are resolved back to known envelopes through an in-process
  index and anything unresolvable is dropped (fail closed): the authoritative
  point-in-time filter in :class:`adapters.graphiti.memory.Memory` re-checks
  every hit.
"""

from __future__ import annotations

import importlib.metadata as metadata
from typing import Any
from uuid import UUID

from adapters.graphiti.errors import (
    GraphitiIngestError,
    GraphitiSearchError,
    GraphitiUnavailableError,
    GraphitiVersionError,
)
from adapters.graphiti.ontology import upstream_edge_models, upstream_entity_models
from adapters.graphiti.pin import (
    UPSTREAM_DISTRIBUTION,
    UPSTREAM_EXTRAS,
    UPSTREAM_VERSION,
)
from adapters.graphiti.schemas import GraphitiConfig, MemoryHit, MemoryRecord, SearchWindow

__all__ = ["LiveGraphitiStore"]

#: Group id Graphiti uses to partition episodes; keeps a backtest's memory
#: isolated from other runs' memories in the same FalkorDB graph.
DEFAULT_GROUP_ID = "opentrading"


def _installed_version() -> str | None:
    """Distribution version of the installed upstream, or None if absent."""
    try:
        return metadata.version(UPSTREAM_DISTRIBUTION)
    except metadata.PackageNotFoundError:
        return None


def _load_upstream() -> tuple[Any, ...]:
    """Import the upstream classes. The single upstream import seam.

    Order: (Graphiti, FalkorDriver, SearchFilters, DateFilter, EpisodeType).
    """
    from graphiti_core import Graphiti  # type: ignore[import-not-found]
    from graphiti_core.driver.falkordb_driver import FalkorDriver  # type: ignore[import-not-found]
    from graphiti_core.nodes import EpisodeType  # type: ignore[import-not-found]
    from graphiti_core.search.search_filters import (  # type: ignore[import-not-found]
        DateFilter,
        SearchFilters,
    )

    return Graphiti, FalkorDriver, SearchFilters, DateFilter, EpisodeType


class LiveGraphitiStore:
    """Graphiti storage backed by FalkorDB (ADR-0008: FalkorDB first).

    Requires ``graphiti-core[falkordb]==<pin>`` installed and a FalkorDB
    reachable at ``config``. An LLM/embedder client is needed for semantic
    extraction and vector search; without one, Graphiti falls back to its
    default clients from the environment.
    """

    def __init__(self, config: GraphitiConfig | None = None, *, check_version: bool = True) -> None:
        self._config = config or GraphitiConfig()
        self._graphiti: Any | None = None
        #: In-process envelope index: episode_id → full record. Search results
        #: are resolved through it and unknown ids are dropped (fail closed).
        self._envelopes: dict[UUID, MemoryRecord] = {}
        if check_version:
            self._verify_pin()

    # ── pin / lifecycle ───────────────────────────────────────────────────

    def _verify_pin(self) -> None:
        installed = _installed_version()
        if installed is None:
            raise GraphitiUnavailableError(
                f"{UPSTREAM_DISTRIBUTION} is not installed; install it with: "
                f'uv pip install "{UPSTREAM_DISTRIBUTION}[{",".join(UPSTREAM_EXTRAS)}]'
                f'=={UPSTREAM_VERSION}"'
            )
        if installed != UPSTREAM_VERSION:
            raise GraphitiVersionError(
                f"installed {UPSTREAM_DISTRIBUTION} {installed!r} does not match "
                f"the pin {UPSTREAM_VERSION!r} (INV-14)"
            )

    def _graph(self) -> Any:
        if self._graphiti is None:
            graphiti_cls, falkor_cls, *_ = _load_upstream()
            driver = falkor_cls(
                host=self._config.host,
                port=self._config.port,
                username=self._config.username,
                password=self._config.password,
                database=self._config.database,
            )
            self._graphiti = graphiti_cls(graph_driver=driver, store_raw_episode_content=True)
        return self._graphiti

    def close(self) -> None:
        """Close the underlying graph driver (idempotent)."""
        if self._graphiti is not None:
            close = getattr(self._graphiti, "close", None)
            if close is not None:
                close()
            self._graphiti = None

    # ── MemoryStore protocol ──────────────────────────────────────────────

    def store(self, record: MemoryRecord) -> None:
        """Write one record into Graphiti. The full envelope is embedded in the
        episode body; ``reference_time`` is the knowledge time (available_time),
        so Graphiti's temporal edges inherit point-in-time semantics."""
        self._envelopes[record.episode_id] = record
        try:
            graph = self._graph()
            _, _, _, _, episode_type = _load_upstream()
            graph.add_episode(
                name=record.summary[:128],
                episode_body=self._body(record),
                source_description=record.source,
                reference_time=record.available_time,
                source=episode_type.text,
                group_id=DEFAULT_GROUP_ID,
                uuid=str(record.episode_id),
                entity_types=upstream_entity_models(),
                edge_types=upstream_edge_models(),
            )
        except (GraphitiIngestError, GraphitiUnavailableError, GraphitiVersionError):
            raise
        except Exception as exc:
            raise GraphitiIngestError(
                f"graphiti add_episode failed for {record.episode_id}"
            ) from exc

    def search(self, query: str, window: SearchWindow) -> tuple[MemoryHit, ...]:
        """Hybrid search with a temporal pushdown; results resolve fail-closed."""
        try:
            _, _, search_filters_cls, date_filter_cls, _ = _load_upstream()
            filters = search_filters_cls(
                valid_at=[date_filter_cls(date=window.as_of, comparison_operator="<=")]
            )
            edges = self._graph().search(
                query,
                num_results=window.limit,
                search_filter=filters,
            )
        except (GraphitiSearchError, GraphitiUnavailableError, GraphitiVersionError):
            raise
        except Exception as exc:
            raise GraphitiSearchError("graphiti search failed") from exc

        by_episode: dict[UUID, MemoryHit] = {}
        for edge in edges or []:
            for raw_uuid in getattr(edge, "episodes", None) or []:
                try:
                    episode_id = UUID(str(raw_uuid))
                except ValueError:
                    continue
                record = self._envelopes.get(episode_id)
                if record is None:  # fail closed: unknown episodes are invisible
                    continue
                by_episode.setdefault(episode_id, MemoryHit(record=record, score=1.0))
        return tuple(by_episode.values())

    # ── internals ─────────────────────────────────────────────────────────

    @staticmethod
    def _body(record: MemoryRecord) -> str:
        """Episode body: human-readable summary plus the machine-readable envelope."""
        return f"{record.summary}\n\n__ENVELOPE__{record.model_dump_json()}"

    @property
    def envelopes(self) -> dict[UUID, MemoryRecord]:
        """Known envelopes (test/debug surface)."""
        return dict(self._envelopes)
