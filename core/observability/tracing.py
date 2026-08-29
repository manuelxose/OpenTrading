"""Langfuse v4 tracing correlated to the canonical domain ``trace_id``."""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, suppress
from typing import Any
from uuid import UUID

_SAFE_METADATA = frozenset(
    {
        "agent",
        "attempt",
        "backend",
        "component",
        "domain_trace_id",
        "event",
        "instrument_id",
        "operation",
        "pipeline",
        "prompt_version",
        "provider",
        "stage",
        "status",
        "strategy_id",
        "tool",
        "version",
    }
)


def deterministic_trace_id(trace_id: UUID) -> str:
    """Return the W3C 16-byte lowercase hexadecimal trace identifier."""
    return trace_id.hex


def _safe_metadata(metadata: Mapping[str, Any] | None, trace_id: UUID) -> dict[str, Any]:
    safe = {key: value for key, value in (metadata or {}).items() if key in _SAFE_METADATA}
    safe["domain_trace_id"] = str(trace_id)
    return safe


class NullObservation:
    def update(self, **kwargs: Any) -> None:
        del kwargs


class _SafeObservation:
    """Prevent telemetry update failures from affecting domain execution."""

    def __init__(self, observation: Any) -> None:
        self._observation = observation

    def update(self, **kwargs: Any) -> None:
        try:
            self._observation.update(**kwargs)
        except Exception:
            return


class LangfuseTracer:
    """Small injectable facade; disabled tracing never affects trading behavior."""

    def __init__(self, *, client: Any | None = None, enabled: bool | None = None) -> None:
        self._client = client
        self._enabled = enabled

    def _get_client(self) -> Any | None:
        if self._enabled is False:
            return None
        if self._client is not None:
            return self._client
        if not os.getenv("LANGFUSE_PUBLIC_KEY") or not os.getenv("LANGFUSE_SECRET_KEY"):
            return None
        try:
            from langfuse import get_client

            return get_client()
        except Exception:
            return None

    @contextmanager
    def observation(
        self,
        *,
        trace_id: UUID,
        name: str,
        as_type: str = "span",
        metadata: Mapping[str, Any] | None = None,
        input: Any | None = None,
        model: str | None = None,
    ) -> Iterator[Any]:
        client = self._get_client()
        if client is None:
            yield NullObservation()
            return
        kwargs: dict[str, Any] = {
            "name": name,
            "as_type": as_type,
            "trace_context": {"trace_id": deterministic_trace_id(trace_id)},
            "metadata": _safe_metadata(metadata, trace_id),
        }
        if input is not None:
            kwargs["input"] = input
        if model is not None:
            kwargs["model"] = model
        try:
            context = client.start_as_current_observation(**kwargs)
            observation = context.__enter__()
        except Exception:
            yield NullObservation()
            return
        try:
            yield _SafeObservation(observation)
        except BaseException as exc:
            with suppress(Exception):
                context.__exit__(type(exc), exc, exc.__traceback__)
            raise
        else:
            with suppress(Exception):
                context.__exit__(None, None, None)


tracer = LangfuseTracer()
