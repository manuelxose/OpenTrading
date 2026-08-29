"""Authenticated operator API for LIVE_GATED approval and emergency controls."""

from collections.abc import Callable
from typing import Annotated, Any, cast
from uuid import UUID

from engines.execution.live_gate import (
    ApprovalRecord,
    HumanApprovalGate,
    KillScope,
    LiveGateViolation,
)
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

__all__ = ["build_live_gated_router"]

OperatorResolver = Callable[..., str]


class DecisionBody(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class KillBody(BaseModel):
    scope: KillScope
    target: str | None = Field(default=None, min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=500)


def _record(record: ApprovalRecord) -> dict[str, object]:
    from dataclasses import asdict

    return cast(dict[str, object], cast(Any, asdict)(record))


def build_live_gated_router(
    gate: HumanApprovalGate, authenticate_operator: OperatorResolver
) -> APIRouter:
    """Build the mutation API; callers must inject a real authentication dependency."""
    router = APIRouter(prefix="/api/v1/live-gated", tags=["live-gated"])
    operator = Annotated[str, Depends(authenticate_operator)]

    @router.get("/approvals/{order_intent_id}")
    def approval_status(order_intent_id: UUID, actor: operator) -> dict[str, object]:
        del actor
        record = gate.get_approval(order_intent_id)
        if record is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="approval not found")
        return _record(record)

    @router.post("/approvals/{order_intent_id}/approve")
    def approve(order_intent_id: UUID, body: DecisionBody, actor: operator) -> dict[str, object]:
        del body
        try:
            return _record(gate.approve(order_intent_id, approver_id=actor))
        except LiveGateViolation as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @router.post("/approvals/{order_intent_id}/reject")
    def reject(order_intent_id: UUID, body: DecisionBody, actor: operator) -> dict[str, object]:
        del body
        try:
            return _record(gate.reject(order_intent_id, approver_id=actor))
        except LiveGateViolation as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    @router.post("/kill-switches", status_code=status.HTTP_204_NO_CONTENT)
    def activate_kill(body: KillBody, actor: operator) -> None:
        try:
            gate.activate_kill(body.scope, actor=actor, reason=body.reason, target=body.target)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc

    @router.delete("/kill-switches/{scope}", status_code=status.HTTP_204_NO_CONTENT)
    def clear_kill(
        scope: KillScope,
        actor: operator,
        reason: str,
        target: str | None = None,
    ) -> None:
        gate.clear_kill(scope, actor=actor, reason=reason, target=target)

    return router
