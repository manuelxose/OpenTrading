"""Authenticated operator API for LIVE_AUTO governance (Phase 11).

Every mutation here requires the operator token and flows through
:class:`LiveAutoRegistry`, which enforces the lifecycle rule
(``LIVE_GATED → LIVE_AUTO`` only), every platform ceiling and the immutable
audit trail. There is deliberately **no endpoint that changes the operating
mode**: the mode comes from ``OT_OPERATING_MODE`` at process start, and no
LLM, RD-Agent or strategy process can touch it.
"""

from decimal import Decimal
from typing import Annotated

from core.domain.enums import StrategyState
from engines.live_auto.config import LiveAutoViolation
from engines.live_auto.registry import LiveAutoRegistry
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from apps.api.live_gated import OperatorResolver

__all__ = ["build_live_auto_router"]


class PromotionBody(BaseModel):
    strategy_id: str = Field(min_length=1, max_length=100)
    strategy_version: str = Field(min_length=1, max_length=100)
    #: Must be LIVE_GATED — the only legal source state (INV-8 / Phase 11).
    from_state: StrategyState = StrategyState.LIVE_GATED
    risk_budget: Decimal = Field(gt=0)
    capital_allocation: Decimal = Field(gt=0)
    evidence: list[str] = Field(default_factory=list)


class DemotionBody(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class PnlBody(BaseModel):
    strategy_id: str = Field(min_length=1, max_length=100)
    amount: Decimal
    source: str = Field(min_length=1, max_length=200)


def build_live_auto_router(
    registry: LiveAutoRegistry, authenticate_operator: OperatorResolver
) -> APIRouter:
    """Build the governance API; callers must inject a real authentication dependency."""
    router = APIRouter(prefix="/api/v1/live-auto", tags=["live-auto"])
    operator = Annotated[str, Depends(authenticate_operator)]

    @router.get("/status")
    def live_auto_status(actor: operator) -> dict[str, object]:
        del actor
        return registry.status()

    @router.post("/promotions", status_code=status.HTTP_201_CREATED)
    def promote(body: PromotionBody, actor: operator) -> dict[str, object]:
        try:
            record = registry.promote(
                strategy_id=body.strategy_id,
                strategy_version=body.strategy_version,
                from_state=body.from_state,
                risk_budget=body.risk_budget,
                capital_allocation=body.capital_allocation,
                actor=actor,
                evidence=tuple(body.evidence),
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        except LiveAutoViolation as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        return {
            "strategy_id": record.strategy_id,
            "strategy_version": record.strategy_version,
            "from_state": record.from_state.value,
            "state": record.state.value,
            "risk_budget": str(record.risk_budget),
            "capital_allocation": str(record.capital_allocation),
            "promoted_by": record.promoted_by,
            "promoted_at": record.promoted_at.isoformat(),
        }

    @router.post("/strategies/{strategy_id}/demote")
    def demote(strategy_id: str, body: DemotionBody, actor: operator) -> dict[str, object]:
        try:
            record = registry.demote(strategy_id=strategy_id, actor=actor, reason=body.reason)
        except LiveAutoViolation as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        return {
            "strategy_id": record.strategy_id,
            "state": record.state.value,
            "active": record.active,
            "demoted_by": record.demoted_by,
            "demoted_at": record.demoted_at.isoformat() if record.demoted_at else None,
        }

    @router.post("/pnl", status_code=status.HTTP_201_CREATED)
    def record_pnl(body: PnlBody, actor: operator) -> dict[str, object]:
        try:
            registry.record_realized_pnl(
                strategy_id=body.strategy_id,
                amount=body.amount,
                actor=actor,
                source=body.source,
            )
        except LiveAutoViolation as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
        return {
            "strategy_id": body.strategy_id,
            "amount": str(body.amount),
            "recorded_by": actor,
            "total_realized_pnl": registry.status()["realized_pnl"],
        }

    return router
