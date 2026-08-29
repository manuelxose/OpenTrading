"""Post-trade analysis & learning engine (architecture §15/§17).

Closed-and-reconciled trade → deterministic metrics (PnL, fees, slippage,
R multiple, alpha, MAE, MFE, holding time, entry/exit efficiency, calibration,
prediction error, regime) → independent quality evaluations (quant / llm /
fused / risk / execution) → expected-vs-actual comparison → postmortem
(PostgreSQL metrics, MinIO artifact, Graphiti lesson, Obsidian note).

Strictly read-only over risk limits (INV-1).
"""

from engines.posttrade.analysis import AnalysisContext, AnalysisResult, PostTradeAnalyzer, analyze
from engines.posttrade.metrics import MetricsInput, PricePoint, compute_trade_metrics

__all__ = [
    "AnalysisContext",
    "AnalysisResult",
    "MetricsInput",
    "PostTradeAnalyzer",
    "PricePoint",
    "analyze",
    "compute_trade_metrics",
]
