"""Strategy Lab: offline self-improvement loop (INV-8).

Loads persisted M1 bars, replays a deterministic parameter grid with the same
signal code the live supervisor runs, ranks candidates and stores immutable
evaluation records. The lab NEVER touches live risk settings or promotes a
strategy — going live remains an operator-audited action.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from itertools import product
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from apps.live_supervisor.bars_store import BarsStore
from apps.live_supervisor.signals import PriceBar, ScalpParams
from apps.strategy_lab.evaluator import ReplayResult, replay

__all__ = ["CandidateEval", "ScalpingGrid", "evaluate_grid", "persist_candidates", "run_lab"]

_SCALPING_GRID: dict[str, object] = {
    "fast_ema": (4, 5, 6, 7, 8),
    "slow_ema": (11, 13, 17, 21),
    "atr_period": (5, 7, 10),
    "min_strength": (Decimal("0.00005"), Decimal("0.0001"), Decimal("0.0002")),
    "stop_ratio": (Decimal("0.8"), Decimal("1.0"), Decimal("1.2"), Decimal("1.5")),
    "take_ratio": (Decimal("1.2"), Decimal("1.5"), Decimal("2.0"), Decimal("3.0")),
}


@dataclass(frozen=True, slots=True)
class ScalpingGrid:
    fast_ema: tuple[int, ...]
    slow_ema: tuple[int, ...]
    atr_period: tuple[int, ...]
    min_strength: tuple[Decimal, ...]
    stop_ratio: tuple[Decimal, ...]
    take_ratio: tuple[Decimal, ...]

    @classmethod
    def aggressive(cls) -> ScalpingGrid:
        return cls(
            fast_ema=(4, 5, 6, 7, 8),
            slow_ema=(11, 13, 17, 21),
            atr_period=(5, 7, 10),
            min_strength=(Decimal("0.00005"), Decimal("0.0001"), Decimal("0.0002")),
            stop_ratio=(Decimal("0.8"), Decimal("1.0"), Decimal("1.2"), Decimal("1.5")),
            take_ratio=(Decimal("1.2"), Decimal("1.5"), Decimal("2.0"), Decimal("3.0")),
        )


@dataclass(frozen=True, slots=True)
class CandidateEval:
    params: ScalpParams
    stop_ratio: Decimal
    take_ratio: Decimal
    result: ReplayResult

    @property
    def score(self) -> Decimal:
        return self.result.score()


def evaluate_grid(
    bars: Sequence[PriceBar], grid: ScalpingGrid, *, spread: Decimal
) -> list[CandidateEval]:
    candidates: list[CandidateEval] = []
    for fast, slow, atr, strength, stop_r, take_r in product(
        grid.fast_ema,
        grid.slow_ema,
        grid.atr_period,
        grid.min_strength,
        grid.stop_ratio,
        grid.take_ratio,
    ):
        if fast >= slow:
            continue
        params = ScalpParams(
            fast_ema=fast, slow_ema=slow, atr_period=atr, min_strength=strength
        )
        result = replay(bars, params, stop_ratio=stop_r, take_ratio=take_r, spread=spread)
        candidates.append(CandidateEval(params, stop_r, take_r, result))
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates


def persist_candidates(
    engine: Engine,
    *,
    strategy_id: str,
    bars_count: int,
    candidates: list[CandidateEval],
    limit: int = 25,
) -> int:
    table = sa.table(
        "strategy_candidates",
        sa.column("candidate_id", sa.Uuid),
        sa.column("strategy_id", sa.Text),
        sa.column("params", sa.JSON),
        sa.column("score", sa.Numeric),
        sa.column("profit_factor", sa.Numeric),
        sa.column("expectancy", sa.Numeric),
        sa.column("trades", sa.Integer),
        sa.column("bars", sa.Integer),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(timezone.utc)
    rows = [
        {
            "candidate_id": uuid4(),
            "strategy_id": strategy_id,
            "params": {
                "fast_ema": c.params.fast_ema,
                "slow_ema": c.params.slow_ema,
                "atr_period": c.params.atr_period,
                "min_strength": str(c.params.min_strength),
                "stop_ratio": str(c.stop_ratio),
                "take_ratio": str(c.take_ratio),
            },
            "score": c.score,
            "profit_factor": c.result.profit_factor,
            "expectancy": c.result.expectancy,
            "trades": c.result.trades,
            "bars": bars_count,
            "created_at": now,
        }
        for c in candidates[:limit]
    ]
    if not rows:
        return 0
    with engine.begin() as conn:
        conn.execute(sa.insert(table), rows)
    return len(rows)


def run_lab(
    settings,
    *,
    strategy_id: str,
    instrument_id: str,
    spread: Decimal,
    grid: ScalpingGrid | None = None,
    top: int = 5,
) -> None:
    from core.config.settings import ensure_psycopg_dsn

    engine = sa.create_engine(ensure_psycopg_dsn(settings.postgres_dsn))
    store = BarsStore(engine)
    bars = store.load_bars(instrument_id)
    print(f"bars loaded: {len(bars)} for {instrument_id}")
    if len(bars) < 80:
        print("not enough bars to evaluate — keep the supervisor collecting data.")
        return

    grid = grid or ScalpingGrid.aggressive()
    candidates = evaluate_grid(bars, grid, spread=spread)
    persisted = persist_candidates(engine, strategy_id=strategy_id, bars_count=len(bars), candidates=candidates)
    print(f"candidates persisted: {persisted} (top {top} below)")
    for rank, candidate in enumerate(candidates[:top], start=1):
        result = candidate.result
        print(
            f"  #{rank} fast={candidate.params.fast_ema} slow={candidate.params.slow_ema} "
            f"atr={candidate.params.atr_period} strength={candidate.params.min_strength} "
            f"stop={candidate.stop_ratio} take={candidate.take_ratio} "
            f"score={candidate.score:.4f} pf={result.profit_factor} "
            f"expectancy={result.expectancy} trades={result.trades}"
        )

    artifact_dir = Path("data/strategy-lab")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "strategy_id": strategy_id,
        "instrument_id": instrument_id,
        "bars": len(bars),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "top": [
            {
                "rank": rank,
                "params": {
                    "fast_ema": c.params.fast_ema,
                    "slow_ema": c.params.slow_ema,
                    "atr_period": c.params.atr_period,
                    "min_strength": str(c.params.min_strength),
                    "stop_ratio": str(c.stop_ratio),
                    "take_ratio": str(c.take_ratio),
                },
                "score": str(c.score),
                "profit_factor": str(c.result.profit_factor) if c.result.profit_factor is not None else None,
                "expectancy": str(c.result.expectancy) if c.result.expectancy is not None else None,
                "trades": c.result.trades,
            }
            for rank, c in enumerate(candidates[:top], start=1)
        ],
    }
    (artifact_dir / "candidates.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("artifact written: data/strategy-lab/candidates.json")
