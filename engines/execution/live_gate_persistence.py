"""Transactional PostgreSQL persistence for LIVE_GATED approvals and kill controls."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from core.config.settings import ensure_psycopg_dsn
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Engine,
    MetaData,
    String,
    Table,
    create_engine,
    insert,
    select,
    update,
)
from sqlalchemy import Uuid as SAUuid
from sqlalchemy.exc import IntegrityError

from engines.execution.live_gate import (
    ApprovalRecord,
    ApprovalStatus,
    KillScope,
    PriceContext,
)

__all__ = ["PostgresApprovalStore", "live_approvals_table", "live_kill_switches_table"]

_metadata = MetaData()
live_approvals_table = Table(
    "live_approvals",
    _metadata,
    Column("order_intent_id", SAUuid, primary_key=True),
    Column("status", String, nullable=False, index=True),
    Column("payload", JSON, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)
live_kill_switches_table = Table(
    "live_kill_switches",
    _metadata,
    Column("scope", String, primary_key=True),
    Column("target", String, primary_key=True),
    Column("actor", String, nullable=False),
    Column("reason", String, nullable=False),
    Column("activated_at", DateTime(timezone=True), nullable=False),
    Column("active", Boolean, nullable=False),
    Column("cleared_by", String, nullable=True),
    Column("clear_reason", String, nullable=True),
    Column("cleared_at", DateTime(timezone=True), nullable=True),
)


class PostgresApprovalStore:
    """Durable store with compare-and-set consumption across worker processes."""

    def __init__(self, dsn: str, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine(ensure_psycopg_dsn(dsn), pool_pre_ping=True)

    def get(self, order_intent_id: UUID) -> ApprovalRecord | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(live_approvals_table.c.payload).where(
                    live_approvals_table.c.order_intent_id == order_intent_id
                )
            ).first()
        return None if row is None else _decode(row.payload)

    def put(self, record: ApprovalRecord) -> ApprovalRecord:
        values = _values(record)
        with self.engine.begin() as conn:
            changed = conn.execute(
                update(live_approvals_table)
                .where(live_approvals_table.c.order_intent_id == record.order_intent_id)
                .values(**values)
            ).rowcount
            if not changed:
                conn.execute(insert(live_approvals_table).values(**values))
        return record

    def put_if_absent(self, record: ApprovalRecord) -> bool:
        try:
            with self.engine.begin() as conn:
                conn.execute(insert(live_approvals_table).values(**_values(record)))
        except IntegrityError:
            return False
        return True

    def compare_and_put(self, expected: ApprovalStatus, record: ApprovalRecord) -> bool:
        with self.engine.begin() as conn:
            changed = conn.execute(
                update(live_approvals_table)
                .where(
                    live_approvals_table.c.order_intent_id == record.order_intent_id,
                    live_approvals_table.c.status == expected.value,
                )
                .values(**_values(record))
            ).rowcount
        return changed == 1

    def active_kills(self) -> set[tuple[KillScope, str | None]]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                select(live_kill_switches_table.c.scope, live_kill_switches_table.c.target).where(
                    live_kill_switches_table.c.active.is_(True)
                )
            ).all()
        return {(KillScope(row.scope), row.target or None) for row in rows}

    def set_kill(
        self, scope: KillScope, target: str | None, actor: str, reason: str, at: datetime
    ) -> None:
        key = target or ""
        values = {
            "scope": scope.value,
            "target": key,
            "actor": actor,
            "reason": reason,
            "activated_at": at,
            "active": True,
            "cleared_by": None,
            "clear_reason": None,
            "cleared_at": None,
        }
        with self.engine.begin() as conn:
            changed = conn.execute(
                update(live_kill_switches_table)
                .where(
                    live_kill_switches_table.c.scope == scope.value,
                    live_kill_switches_table.c.target == key,
                )
                .values(**values)
            ).rowcount
            if not changed:
                conn.execute(insert(live_kill_switches_table).values(**values))

    def clear_kill(
        self,
        scope: KillScope,
        target: str | None,
        actor: str,
        reason: str,
        at: datetime,
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                update(live_kill_switches_table)
                .where(
                    live_kill_switches_table.c.scope == scope.value,
                    live_kill_switches_table.c.target == (target or ""),
                )
                .values(active=False, cleared_by=actor, clear_reason=reason, cleared_at=at)
            )


def _values(record: ApprovalRecord) -> dict[str, Any]:
    return {
        "order_intent_id": record.order_intent_id,
        "status": record.status.value,
        "payload": _encode(record),
        "updated_at": record.consumed_at or record.approved_at or record.requested_at,
    }


def _encode(record: ApprovalRecord) -> dict[str, Any]:
    return {
        "approval_id": str(record.approval_id),
        "order_intent_id": str(record.order_intent_id),
        "risk_decision_id": str(record.risk_decision_id),
        "strategy_id": record.strategy_id,
        "strategy_version": record.strategy_version,
        "instrument_id": record.instrument_id,
        "intent_hash": record.intent_hash,
        "price_context": record.price_context.model_dump(mode="json"),
        "requested_at": record.requested_at.isoformat(),
        "expires_at": record.expires_at.isoformat(),
        "status": record.status.value,
        "approver_id": record.approver_id,
        "approved_at": record.approved_at.isoformat() if record.approved_at else None,
        "consumed_at": record.consumed_at.isoformat() if record.consumed_at else None,
        "signature": record.signature,
        "invalidation_reason": record.invalidation_reason,
    }


def _decode(raw: dict[str, Any]) -> ApprovalRecord:
    return ApprovalRecord(
        approval_id=UUID(raw["approval_id"]),
        order_intent_id=UUID(raw["order_intent_id"]),
        risk_decision_id=UUID(raw["risk_decision_id"]),
        strategy_id=str(raw["strategy_id"]),
        strategy_version=str(raw["strategy_version"]),
        instrument_id=str(raw["instrument_id"]),
        intent_hash=str(raw["intent_hash"]),
        price_context=PriceContext.model_validate(raw["price_context"]),
        requested_at=datetime.fromisoformat(raw["requested_at"]),
        expires_at=datetime.fromisoformat(raw["expires_at"]),
        status=ApprovalStatus(raw["status"]),
        approver_id=raw.get("approver_id"),
        approved_at=(
            datetime.fromisoformat(raw["approved_at"]) if raw.get("approved_at") else None
        ),
        consumed_at=(
            datetime.fromisoformat(raw["consumed_at"]) if raw.get("consumed_at") else None
        ),
        signature=raw.get("signature"),
        invalidation_reason=raw.get("invalidation_reason"),
    )
