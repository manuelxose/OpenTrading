"""Authenticated operator API for the emergency control system (INV-7).

Mounts only in LIVE_GATED mode behind the same operator token as the
live-gated approval API. Read endpoints expose the persisted state; mutations
activate / deactivate the four emergency levels and are fully audited by the
controller.

The emergency controls themselves are independent of this API: they live in
:mod:`engines.execution.emergency` and keep working even when the API process,
LLM processes or strategy processes are down.
"""

from __future__ import annotations

from typing import Annotated, Any

from core.domain.enums import EmergencyLevel
from engines.execution.emergency import EmergencyController
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from apps.api.live_gated import OperatorResolver

__all__ = ["build_emergency_router"]


class EmergencyBody(BaseModel):
    level: EmergencyLevel
    target: str | None = Field(default=None, min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=500)


def build_emergency_router(
    emergency: EmergencyController, authenticate_operator: OperatorResolver
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/emergency", tags=["emergency"])
    operator = Annotated[str, Depends(authenticate_operator)]

    @router.get("/state")
    def state(actor: operator) -> dict[str, Any]:
        del actor
        return emergency.snapshot()

    @router.post("/controls", status_code=status.HTTP_204_NO_CONTENT)
    def activate(body: EmergencyBody, actor: operator) -> None:
        try:
            emergency.activate(body.level, target=body.target, actor=actor, reason=body.reason)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc

    @router.delete("/controls/{level}", status_code=status.HTTP_204_NO_CONTENT)
    def deactivate(
        level: EmergencyLevel,
        actor: operator,
        reason: str,
        target: str | None = None,
    ) -> None:
        try:
            emergency.deactivate(level, target=target, actor=actor, reason=reason)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc

    return router
