"""Persistence for the emergency control system (INV-7, architecture §10).

Two SQLAlchemy Core tables mirror the pydantic contracts in
:mod:`core.schemas.execution`:

- ``emergency_controls`` — one row per ``(level, target)``; deactivations keep
  the row with ``active=false`` so the full activation history is auditable.
- ``emergency_dead_man`` — the dead man switch singleton row: heartbeat
  timestamps and the safe-execution-state flag.

Alembic migration ``0007_emergency_controls`` mirrors these definitions
(self-contained DDL, per repo convention); keep both in sync on change.

Unit tests inject :class:`InMemoryEmergencyStore` (no PostgreSQL in CI);
:class:`PostgresEmergencyStore` is exercised by the docker-gated integration
suite.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

from core.config.settings import ensure_psycopg_dsn
from core.domain.enums import EmergencyLevel
from core.schemas.execution import DeadManSwitchState, EmergencyControlState
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Engine,
    Float,
    Integer,
    MetaData,
    Table,
    Text,
    create_engine,
    select,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB

__all__ = [
    "DEAD_MAN_SINGLETON_ID",
    "EmergencyStore",
    "InMemoryEmergencyStore",
    "PostgresEmergencyStore",
    "emergency_controls_table",
    "emergency_dead_man_table",
]

DEAD_MAN_SINGLETON_ID = 1

metadata = MetaData()

emergency_controls_table = Table(
    "emergency_controls",
    metadata,
    Column("level", Text, primary_key=True),
    Column("target", Text, primary_key=True),
    Column("active", Boolean, nullable=False),
    Column("activated_by", Text, nullable=False),
    Column("activated_at", DateTime(timezone=True), nullable=False),
    Column("reason", Text, nullable=False),
    Column("deactivated_by", Text, nullable=True),
    Column("deactivate_reason", Text, nullable=True),
    Column("deactivated_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

emergency_dead_man_table = Table(
    "emergency_dead_man",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("dead_man_switch_enabled", Boolean, nullable=False),
    Column("heartbeat_timeout_seconds", Float, nullable=False),
    Column("armed_at", DateTime(timezone=True), nullable=False),
    Column("last_heartbeat_at", DateTime(timezone=True), nullable=True),
    Column("safe_execution_state", Boolean, nullable=False),
    Column("heartbeat_lost_at", DateTime(timezone=True), nullable=True),
    Column("reason_codes", JSONB, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

#: Earliest representable timestamp, used as the "absent" placeholder.
_EPOCH = datetime.min.replace(tzinfo=UTC)


def _empty_dead_man(now: datetime, *, enabled: bool, timeout: timedelta) -> DeadManSwitchState:
    return DeadManSwitchState(
        dead_man_switch_enabled=enabled,
        heartbeat_timeout_seconds=timeout.total_seconds(),
        armed_at=now,
        updated_at=now,
    )


class EmergencyStore(Protocol):
    """Authoritative emergency-control persistence boundary (INV-7)."""

    def list_active_controls(self) -> tuple[EmergencyControlState, ...]: ...

    def get_control(
        self, level: EmergencyLevel, target: str | None = None
    ) -> EmergencyControlState | None: ...

    def set_control(self, state: EmergencyControlState) -> EmergencyControlState: ...

    def clear_control(
        self,
        level: EmergencyLevel,
        target: str | None,
        *,
        actor: str,
        reason: str,
        at: datetime,
    ) -> EmergencyControlState: ...

    def get_dead_man(self) -> DeadManSwitchState: ...

    def set_dead_man(self, state: DeadManSwitchState) -> DeadManSwitchState: ...


class InMemoryEmergencyStore:
    """Deterministic in-memory store with the same semantics as PostgreSQL."""

    def __init__(self) -> None:
        self._controls: dict[tuple[EmergencyLevel, str | None], EmergencyControlState] = {}
        self._dead_man: DeadManSwitchState | None = None

    def list_active_controls(self) -> tuple[EmergencyControlState, ...]:
        return tuple(
            sorted(
                (c for c in self._controls.values() if c.active),
                key=lambda c: (c.level.value, c.target or ""),
            )
        )

    def get_control(
        self, level: EmergencyLevel, target: str | None = None
    ) -> EmergencyControlState | None:
        return self._controls.get((level, target))

    def set_control(self, state: EmergencyControlState) -> EmergencyControlState:
        self._controls[(state.level, state.target)] = state
        return state

    def clear_control(
        self,
        level: EmergencyLevel,
        target: str | None,
        *,
        actor: str,
        reason: str,
        at: datetime,
    ) -> EmergencyControlState:
        current = self._controls.get((level, target))
        if current is None:
            return EmergencyControlState(
                level=level,
                target=target,
                active=False,
                activated_by=actor,
                activated_at=at,
                reason=reason,
                deactivated_by=actor,
                deactivate_reason=reason,
                deactivated_at=at,
                updated_at=at,
            )
        cleared = current.model_copy(
            update={
                "active": False,
                "deactivated_by": actor,
                "deactivate_reason": reason,
                "deactivated_at": at,
                "updated_at": at,
            }
        )
        self._controls[(level, target)] = cleared
        return cleared

    def get_dead_man(self) -> DeadManSwitchState:
        return (
            self._dead_man
            if self._dead_man is not None
            else _empty_dead_man(_EPOCH, enabled=True, timeout=timedelta(seconds=1))
        )

    def set_dead_man(self, state: DeadManSwitchState) -> DeadManSwitchState:
        self._dead_man = state
        return state


_CONTROL_COLUMNS = tuple(emergency_controls_table.c)


def _row_to_control(row: object) -> EmergencyControlState:
    values = {column.key: getattr(row, column.key) for column in _CONTROL_COLUMNS}
    if not values["target"]:
        values["target"] = None
    return EmergencyControlState.model_validate(values)


def _control_values(state: EmergencyControlState) -> dict[str, object]:
    values = state.model_dump(mode="json")
    values["target"] = state.target or ""
    return values


def _row_to_dead_man(row: object) -> DeadManSwitchState:
    values = {column.key: getattr(row, column.key) for column in emergency_dead_man_table.c}
    values.pop("id", None)  # singleton PK column is not part of the state schema
    values["reason_codes"] = tuple(values.get("reason_codes") or ())
    return DeadManSwitchState.model_validate(values)


def _dead_man_values(state: DeadManSwitchState) -> dict[str, object]:
    return {
        "dead_man_switch_enabled": state.dead_man_switch_enabled,
        "heartbeat_timeout_seconds": state.heartbeat_timeout_seconds,
        "armed_at": state.armed_at,
        "last_heartbeat_at": state.last_heartbeat_at,
        "safe_execution_state": state.safe_execution_state,
        "heartbeat_lost_at": state.heartbeat_lost_at,
        "reason_codes": list(state.reason_codes),
        "updated_at": state.updated_at,
    }


class PostgresEmergencyStore:
    """SQLAlchemy Core store against PostgreSQL (transactional source of truth)."""

    def __init__(self, dsn: str, engine: Engine | None = None) -> None:
        self._engine: Engine = engine or create_engine(ensure_psycopg_dsn(dsn))

    def list_active_controls(self) -> tuple[EmergencyControlState, ...]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(emergency_controls_table)
                .where(emergency_controls_table.c.active.is_(True))
                .order_by("level", "target")
            ).all()
        return tuple(_row_to_control(row) for row in rows)

    def get_control(
        self, level: EmergencyLevel, target: str | None = None
    ) -> EmergencyControlState | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(emergency_controls_table).where(
                    emergency_controls_table.c.level == level.value,
                    emergency_controls_table.c.target == (target or ""),
                )
            ).first()
        return _row_to_control(row) if row is not None else None

    def set_control(self, state: EmergencyControlState) -> EmergencyControlState:
        values = _control_values(state)
        with self._engine.begin() as conn:
            conn.execute(
                postgresql.insert(emergency_controls_table)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=["level", "target"],
                    set_={k: values[k] for k in values if k not in ("level", "target")},
                )
            )
        return state

    def clear_control(
        self,
        level: EmergencyLevel,
        target: str | None,
        *,
        actor: str,
        reason: str,
        at: datetime,
    ) -> EmergencyControlState:
        key = target or ""
        with self._engine.begin() as conn:
            current = conn.execute(
                select(emergency_controls_table).where(
                    emergency_controls_table.c.level == level.value,
                    emergency_controls_table.c.target == key,
                )
            ).first()
            if current is None:
                values = {
                    "level": level.value,
                    "target": key,
                    "active": False,
                    "activated_by": actor,
                    "activated_at": at,
                    "reason": reason,
                    "deactivated_by": actor,
                    "deactivate_reason": reason,
                    "deactivated_at": at,
                    "updated_at": at,
                }
                conn.execute(emergency_controls_table.insert().values(**values))
                return EmergencyControlState.model_validate(
                    {**values, "level": level, "target": target}
                )
            # Preserve the original activation history; only record the clearing.
            conn.execute(
                emergency_controls_table.update()
                .where(
                    emergency_controls_table.c.level == level.value,
                    emergency_controls_table.c.target == key,
                )
                .values(
                    active=False,
                    deactivated_by=actor,
                    deactivate_reason=reason,
                    deactivated_at=at,
                    updated_at=at,
                )
            )
        return EmergencyControlState(
            level=EmergencyLevel(current.level),
            target=current.target or None,
            active=False,
            activated_by=current.activated_by,
            activated_at=current.activated_at,
            reason=current.reason,
            deactivated_by=actor,
            deactivate_reason=reason,
            deactivated_at=at,
            updated_at=at,
        )

    def get_dead_man(self) -> DeadManSwitchState:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(emergency_dead_man_table).where(
                    emergency_dead_man_table.c.id == DEAD_MAN_SINGLETON_ID
                )
            ).first()
        if row is None:
            return _empty_dead_man(_EPOCH, enabled=True, timeout=timedelta(seconds=1))
        return _row_to_dead_man(row)

    def set_dead_man(self, state: DeadManSwitchState) -> DeadManSwitchState:
        values = _dead_man_values(state)
        with self._engine.begin() as conn:
            result = conn.execute(
                emergency_dead_man_table.update()
                .where(emergency_dead_man_table.c.id == DEAD_MAN_SINGLETON_ID)
                .values(**values)
            )
            if result.rowcount != 1:
                conn.execute(
                    emergency_dead_man_table.insert().values(id=DEAD_MAN_SINGLETON_ID, **values)
                )
        return state
