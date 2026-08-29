"""Independent signal-quality evaluation in the post-trade analyzer."""

from __future__ import annotations

from datetime import UTC, datetime

from core.domain.enums import SignalDirection
from engines.posttrade.analysis import AnalysisContext, analyze

from factories import make_llm_signal, make_trade_outcome


def test_flat_signal_is_excluded_from_directional_calibration() -> None:
    now = datetime(2026, 8, 27, tzinfo=UTC)
    result = analyze(
        AnalysisContext(
            outcome=make_trade_outcome(now),
            strategy_id="strategy-01",
            strategy_version="3.1.0",
            llm=make_llm_signal(now, direction=SignalDirection.FLAT, confidence=0.9),
        )
    )

    llm_quality = next(quality for quality in result.signal_quality if quality.producer == "llm")
    assert llm_quality.direction_correct is None
    assert llm_quality.brier_error is None
    assert "llm" not in result.metrics.signal_calibration_error
