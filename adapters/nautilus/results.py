"""Backtest result container with reproducibility fingerprints (ADR-0007 DoD).

``input_hash`` binds dataset + config + code SHA; ``output_hash`` binds every
domain output. Two runs with the same input hash MUST produce the same output
hash (enforced by the determinism tests).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal

from core.schemas import ExecutionReport, PositionSnapshot, TradeOutcome
from pydantic import BaseModel

from adapters.nautilus.metrics import EquityPoint, PortfolioMetrics

__all__ = ["BacktestRunResult", "compute_output_hash", "input_fingerprint"]


def input_fingerprint(dataset_hash: str, config_hash: str, code_sha: str) -> str:
    return hashlib.sha256(f"{dataset_hash}|{config_hash}|{code_sha}".encode()).hexdigest()


def compute_output_hash(
    reports: list[ExecutionReport],
    outcomes: list[TradeOutcome],
    final_positions: list[PositionSnapshot],
    equity_curve: list[EquityPoint],
    metrics: PortfolioMetrics,
    final_balances: dict[str, Decimal],
) -> str:
    """Canonical sha256 over all domain outputs of a run."""
    payload = {
        "reports": [r.canonical_dict() for r in reports],
        "outcomes": [o.canonical_dict() for o in outcomes],
        "final_positions": [p.canonical_dict() for p in final_positions],
        "equity_curve": [[p.ts.isoformat(), str(p.equity)] for p in equity_curve],
        "metrics": metrics.model_dump(mode="json"),
        "final_balances": {k: str(v) for k, v in sorted(final_balances.items())},
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class BacktestRunResult(BaseModel):
    """Everything a single BACKTEST run produced, plus its fingerprints."""

    dataset_hash: str
    config_hash: str
    code_sha: str
    input_hash: str
    output_hash: str
    venue: str
    instrument_id: str
    start_time: datetime
    end_time: datetime
    execution_reports: list[ExecutionReport]
    trade_outcomes: list[TradeOutcome]
    final_positions: list[PositionSnapshot]
    equity_curve: list[EquityPoint]
    final_balances: dict[str, Decimal]
    venue_balances: dict[str, Decimal] | None = None
    metrics: PortfolioMetrics
