"""Temporal memory errors (ADR-0008, INV-3).

Concrete error types so callers can distinguish "upstream unavailable", "ontology
violation", "temporally impossible record" and "leakage attempt" without string
matching.
"""

from __future__ import annotations


class GraphitiError(Exception):
    """Base class for every temporal memory error."""


class GraphitiUnavailableError(GraphitiError):
    """Upstream Graphiti (or FalkorDB) could not be reached or imported."""


class GraphitiVersionError(GraphitiError):
    """The installed graphiti-core distribution does not match the pin (INV-14)."""


class GraphitiIngestError(GraphitiError):
    """An episode could not be written to the graph store."""


class GraphitiSearchError(GraphitiError):
    """A search against the graph store failed."""


class GraphitiResolutionError(GraphitiError):
    """A store result could not be resolved back to a known memory record."""


class OntologyError(GraphitiError):
    """An entity type or relation is not part of the frozen trading ontology."""


class TemporalOrderingError(GraphitiError):
    """The temporal envelope is impossible: event_time <= available_time <= ingested_at
    is violated (an event cannot be known before it happens, nor ingested before it is
    available)."""


class LayerPolicyError(GraphitiError):
    """A tier policy parameter is inconsistent (e.g. overlapping reach windows)."""


class FutureMemoryLeakageError(GraphitiError):
    """INV-3 violation: an episode with available_time > as_of reached the query surface.
    Raised by defense-in-depth guards, never as the primary filter mechanism (that is
    :class:`adapters.graphiti.memory.PointInTimeFilter`)."""
