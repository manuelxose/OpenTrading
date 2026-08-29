"""Deterministic Risk & Policy Engine (architecture §7, INV-4).

100% own deterministic code — no LLM, no agent, no prompt-based decisions.
Outputs ``RiskDecision`` (APPROVE | RESIZE | REJECT) with deterministic reason
codes; the approved quantity is always computed by the engine (INV-1).
"""

from engines.risk.checks import RiskEngineInputError
from engines.risk.engine import (
    RISK_ENGINE_VERSION,
    RiskEngine,
    compute_inputs_hash,
    evaluate_proposal,
)

__all__ = [
    "RISK_ENGINE_VERSION",
    "RiskEngine",
    "RiskEngineInputError",
    "compute_inputs_hash",
    "evaluate_proposal",
]
