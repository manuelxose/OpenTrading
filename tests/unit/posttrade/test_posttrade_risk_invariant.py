"""INV-1: post-trade analysis never modifies live risk limits.

Two layers of defense:

1. **Static** — ``engines/posttrade`` must not import the risk engine or the
   ``RiskPolicy`` contract at all; it only consumes the read-only
   ``RiskDecision`` payload that was produced at entry.
2. **Behavioral** — running a full analysis leaves its inputs byte-identical
   (frozen contracts; a future mutation path would be caught here too).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from core.domain.enums import SignalDirection
from engines.posttrade.analysis import AnalysisContext, analyze

from factories import (
    make_fused_signal,
    make_llm_signal,
    make_quant_signal,
    make_risk_decision_approve,
    make_trade_outcome,
)

ENGINE_ROOT = Path(__file__).resolve().parents[3] / "engines" / "posttrade"


def test_posttrade_engine_never_imports_risk_writers() -> None:
    sources = [path for path in ENGINE_ROOT.rglob("*.py") if "__pycache__" not in str(path)]
    assert sources, "engines/posttrade sources missing"
    for path in sources:
        text = path.read_text(encoding="utf-8")
        assert "engines.risk" not in text, f"{path.name} imports the risk engine"
        assert "RiskPolicy" not in text, f"{path.name} touches RiskPolicy"
        assert "upsert_policy" not in text, f"{path.name} calls a policy writer"


def test_analysis_leaves_risk_decision_unchanged() -> None:
    now = datetime(2026, 8, 27, tzinfo=UTC)
    decision = make_risk_decision_approve(now, risk_amount=Decimal("20.00"))
    before = decision.model_dump(mode="json")
    context = AnalysisContext(
        outcome=make_trade_outcome(now, direction=SignalDirection.LONG),
        strategy_id="paper-baseline-001",
        strategy_version="1.0.0",
        entry_stop=Decimal("1.07800"),
        entry_take=Decimal("1.08600"),
        risk_decision=decision,
        quant=make_quant_signal(now, direction=SignalDirection.LONG),
        llm=make_llm_signal(now, direction=SignalDirection.LONG),
        fused=make_fused_signal(now, direction=SignalDirection.LONG),
    )
    analyze(context)
    assert decision.model_dump(mode="json") == before
