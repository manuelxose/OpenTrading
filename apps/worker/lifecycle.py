"""Trade lifecycle transition helpers (Phase 7).

All lifecycle mutations flow through :func:`transition`, which enforces the
canonical machine (``TRADE_LIFECYCLE_TRANSITIONS``) and compare-and-set
versioning. Redeliveries (worker restarts) hit the store's CAS guard and are
treated as already-done — transitions are never double-applied.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from core.domain.enums import TradeLifecycleState
from core.domain.state_machines import InvalidStateTransition, is_valid_trade_transition
from core.schemas.pipeline import TradeLifecycle

from apps.worker.persistence import StalePipelineStateError
from apps.worker.stages.base import StageRuntime

__all__ = ["transition", "transition_chain"]

logger = logging.getLogger(__name__)


def transition(
    rt: StageRuntime,
    trace_id: UUID,
    target: TradeLifecycleState,
    *,
    fields: dict[str, Any] | None = None,
    required_from: TradeLifecycleState | None = None,
) -> TradeLifecycle | None:
    """Move the trace's lifecycle to ``target`` if the canonical machine allows it.

    Returns the updated lifecycle, or ``None`` when the trace has no lifecycle
    or the transition was already applied by a previous (redelivered) attempt.
    """
    lifecycle = rt.store.get_lifecycle_by_trace(trace_id)
    if lifecycle is None:
        return None
    current = lifecycle.state
    if required_from is not None and current is not required_from:
        return None
    if current is target:
        return lifecycle  # already there (idempotent)
    if not is_valid_trade_transition(current, target):
        logger.warning(
            "refusing invalid lifecycle transition %s -> %s (trace %s)",
            current.value,
            target.value,
            trace_id,
        )
        raise InvalidStateTransition(current.value, target.value)
    now = rt.clock.now()
    updated = lifecycle.model_copy(
        update={
            "state": target,
            "version": lifecycle.version + 1,
            "updated_at": now,
            **(fields or {}),
        }
    )
    try:
        return rt.store.update_lifecycle(updated, lifecycle.version)
    except StalePipelineStateError:
        return None  # another delivery already applied it


def transition_chain(
    rt: StageRuntime,
    trace_id: UUID,
    targets: tuple[TradeLifecycleState, ...],
    *,
    fields: dict[str, Any] | None = None,
) -> TradeLifecycle | None:
    """Apply a sequence of transitions in order (each CAS-guarded)."""
    result = None
    for target in targets:
        result = transition(rt, trace_id, target, fields=fields)
        if result is None:
            break
    return result
