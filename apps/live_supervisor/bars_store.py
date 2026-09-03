"""M1 bar persistence for the Strategy Lab (write path: supervisor; read path: lab)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.engine import Engine

from apps.live_supervisor.signals import PriceBar

__all__ = ["BarsStore"]

_UPSERT = text(
    """
    INSERT INTO strategy_lab_bars (instrument_id, minute, open, high, low, close, recorded_at)
    VALUES (:instrument_id, :minute, :open, :high, :low, :close, :recorded_at)
    ON CONFLICT (instrument_id, minute) DO NOTHING
    """
)


class BarsStore:
    """Upsert closed minute bars (idempotent; bars are never overwritten)."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def upsert_bars(self, instrument_id: str, bars: tuple[PriceBar, ...]) -> int:
        if not bars:
            return 0
        now = datetime.now().astimezone()
        rows = [
            {
                "instrument_id": instrument_id,
                "minute": bar.closed_at,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "recorded_at": now,
            }
            for bar in bars
        ]
        with self._engine.begin() as conn:
            conn.execute(_UPSERT, rows)
        return len(rows)

    def load_bars(self, instrument_id: str, *, limit: int | None = None) -> list[PriceBar]:
        clause = text(
            "SELECT minute, open, high, low, close FROM strategy_lab_bars "
            "WHERE instrument_id = :iid ORDER BY minute ASC"
            + (f" LIMIT {int(limit)}" if limit else "")
        )
        with self._engine.connect() as conn:
            rows = conn.execute(clause, {"iid": instrument_id}).all()
        return [
            PriceBar(
                open=Decimal(row.open),
                high=Decimal(row.high),
                low=Decimal(row.low),
                close=Decimal(row.close),
                closed_at=row.minute,
            )
            for row in rows
        ]
