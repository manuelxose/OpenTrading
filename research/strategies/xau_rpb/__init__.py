"""XAU_RPB — Regime-Filtered Pullback -> Breakout for XAUUSD.

The **canonical** implementation of the strategy frozen in
``docs/strategy/XAUUSD_RPB_SPEC.md``. The MQL4 expert advisor
(``mt4/Experts/XauRpbEA.mq4``) is a mirror of this package and is held to it by
the signal-parity tests in ``tests/parity/``.

Status: RESEARCH. No statistical qualification has been performed — see
``docs/strategy/RESEARCH_REPORT.md`` for the evidence-based status and the gates
that remain unmet.
"""

from __future__ import annotations

from .backtest import BacktestResult, aggregate_h1, run_backtest
from .config import (
    SPEC_VERSION,
    ExecutionParams,
    OperationalParams,
    ResearchParams,
    RiskPolicyParams,
    StrategyConfig,
    StructuralParams,
)
from .news import NewsCalendar
from .regime import RegimeFeatures, RegimeSeries, classify
from .risk_limits import RiskGovernor, RiskState
from .scoring import MAX_SCORE, compute_score
from .sessions import SessionResolver
from .sizing import SizingResult, calculate_lots
from .state_machine import SetupMachine
from .types import (
    Bar,
    BrokerSpec,
    Direction,
    ExitReason,
    Regime,
    RejectReason,
    SetupState,
    Trade,
)

__all__ = [
    "MAX_SCORE",
    "SPEC_VERSION",
    "BacktestResult",
    "Bar",
    "BrokerSpec",
    "Direction",
    "ExecutionParams",
    "ExitReason",
    "NewsCalendar",
    "OperationalParams",
    "Regime",
    "RegimeFeatures",
    "RegimeSeries",
    "RejectReason",
    "ResearchParams",
    "RiskGovernor",
    "RiskPolicyParams",
    "RiskState",
    "SessionResolver",
    "SetupMachine",
    "SetupState",
    "SizingResult",
    "StrategyConfig",
    "StructuralParams",
    "Trade",
    "aggregate_h1",
    "calculate_lots",
    "classify",
    "compute_score",
    "run_backtest",
]
