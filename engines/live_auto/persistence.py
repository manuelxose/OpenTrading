"""PostgreSQL persistence for the LIVE_AUTO registry and PnL ledger (0008).

The registry rows and the ledger are transactional source of truth (INV-10).
``PostgresLiveAutoStore`` is the only writer; strategy processes, LLMs and
RD-Agent have no path to these tables.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from core.config.settings import ensure_psycopg_dsn
from core.domain.enums import StrategyState
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    MetaData,
    Numeric,
    Table,
    Text,
    create_engine,
    func,
    insert,
    select,
    update,
)
from sqlalchemy import Uuid as SAUuid
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from engines.live_auto.registry import LiveAutoStrategyRecord

__all__ = [
    "PostgresLiveAutoStore",
    "live_auto_pnl_ledger_table",
    "live_auto_strategies_table",
]

_metadata = MetaData()
live_auto_strategies_table = Table(
    "live_auto_strategies",
    _metadata,
    Column("strategy_id", Text, primary_key=True),
    Column("strategy_version", Text, nullable=False),
    Column("from_state", Text, nullable=False),
    Column("state", Text, nullable=False),
    Column("risk_budget", Numeric(38, 8), nullable=False),
    Column("capital_allocation", Numeric(38, 8), nullable=False),
    Column("promoted_by", Text, nullable=False),
    Column("promoted_at", DateTime(timezone=True), nullable=False),
    Column("evidence", JSON, nullable=False),
    Column("active", Boolean, nullable=False),
    Column("demoted_by", Text, nullable=True),
    Column("demoted_at", DateTime(timezone=True), nullable=True),
    Column("demote_reason", Text, nullable=True),
)
live_auto_pnl_ledger_table = Table(
    "live_auto_pnl_ledger",
    _metadata,
    Column("ledger_id", SAUuid, nullable=False, unique=True),
    Column("strategy_id", Text, nullable=False),
    Column("amount", Numeric(38, 8), nullable=False),
    Column("recorded_by", Text, nullable=False),
    Column("recorded_at", DateTime(timezone=True), nullable=False),
    Column("source", Text, nullable=False),
)


class PostgresLiveAutoStore:
    """Durable registry store; insert-or-update is CAS-guarded by strategy id."""

    def __init__(self, dsn: str, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine(ensure_psycopg_dsn(dsn), pool_pre_ping=True)

    def get_strategy(self, strategy_id: str) -> LiveAutoStrategyRecord | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(live_auto_strategies_table).where(
                    live_auto_strategies_table.c.strategy_id == strategy_id
                )
            ).first()
        return None if row is None else _decode_strategy(row._mapping)

    def save_strategy(self, record: LiveAutoStrategyRecord) -> None:
        values = _encode_strategy(record)
        with self.engine.begin() as conn:
            changed = conn.execute(
                update(live_auto_strategies_table)
                .where(live_auto_strategies_table.c.strategy_id == record.strategy_id)
                .values(**values)
            ).rowcount
            if not changed:
                try:
                    with self.engine.begin() as conn:
                        conn.execute(insert(live_auto_strategies_table).values(**values))
                except IntegrityError:
                    # Concurrent first write won the insert: retry the update once.
                    with self.engine.begin() as conn:
                        conn.execute(
                            update(live_auto_strategies_table)
                            .where(
                                live_auto_strategies_table.c.strategy_id == record.strategy_id
                            )
                            .values(**values)
                        )

    def list_strategies(self) -> tuple[LiveAutoStrategyRecord, ...]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(live_auto_strategies_table)).all()
        return tuple(_decode_strategy(row._mapping) for row in rows)

    def append_pnl(
        self,
        *,
        ledger_id: UUID,
        strategy_id: str,
        amount: Decimal,
        recorded_by: str,
        recorded_at: datetime,
        source: str,
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                insert(live_auto_pnl_ledger_table).values(
                    ledger_id=ledger_id,
                    strategy_id=strategy_id,
                    amount=amount,
                    recorded_by=recorded_by,
                    recorded_at=recorded_at,
                    source=source,
                )
            )

    def total_pnl(self) -> Decimal:
        with self.engine.connect() as conn:
            total = conn.execute(
                select(func.coalesce(func.sum(live_auto_pnl_ledger_table.c.amount), 0))
            ).scalar_one()
        return Decimal(total) if total is not None else Decimal("0")


def _decode_strategy(row: Any) -> LiveAutoStrategyRecord:
    mapping: dict[str, Any] = dict(row._mapping)
    return LiveAutoStrategyRecord(
        strategy_id=mapping["strategy_id"],
        strategy_version=mapping["strategy_version"],
        from_state=StrategyState(mapping["from_state"]),
        state=StrategyState(mapping["state"]),
        risk_budget=Decimal(mapping["risk_budget"]),
        capital_allocation=Decimal(mapping["capital_allocation"]),
        promoted_by=mapping["promoted_by"],
        promoted_at=mapping["promoted_at"],
        evidence=tuple(mapping["evidence"]),
        active=bool(mapping["active"]),
        demoted_by=mapping.get("demoted_by"),
        demoted_at=mapping.get("demoted_at"),
        demote_reason=mapping.get("demote_reason"),
    )


def _encode_strategy(record: LiveAutoStrategyRecord) -> dict[str, object]:
    return {
        "strategy_id": record.strategy_id,
        "strategy_version": record.strategy_version,
        "from_state": record.from_state.value,
        "state": record.state.value,
        "risk_budget": record.risk_budget,
        "capital_allocation": record.capital_allocation,
        "promoted_by": record.promoted_by,
        "promoted_at": record.promoted_at,
        "evidence": list(record.evidence),
        "active": record.active,
        "demoted_by": record.demoted_by,
        "demoted_at": record.demoted_at,
        "demote_reason": record.demote_reason,
    }
