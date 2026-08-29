"""NautilusTrader adapter — Phase 4, deterministic backtest/paper venue (ADR-0007).

BACKTEST mode runs on the Nautilus virtual clock with historical replay,
realistic commissions, configurable spread/slippage, order rejection simulation,
position accounting and reproducible seeds. The canonical ``OrderIntent`` is the
only object that crosses the boundary (INV-2) — the same interface will serve
PAPER and LIVE venues.
"""

from adapters.nautilus.config import (
    BacktestConfig,
    BaselineSmaConfig,
    CommissionConfig,
    DatasetConfig,
    RejectionConfig,
    SlippageConfig,
    SpreadConfig,
)
from adapters.nautilus.dataset import Dataset, build_dataset
from adapters.nautilus.engine import NautilusBacktestRunner, code_sha, eurusd_instrument
from adapters.nautilus.mapping import (
    instrument_to_nautilus,
    order_intent_to_order,
    report_from_order_accepted,
    report_from_order_filled,
    report_from_order_rejected,
    snapshot_from_position_event,
    trade_outcome_from_position_closed,
)
from adapters.nautilus.metrics import PortfolioMetrics, compute_metrics
from adapters.nautilus.results import BacktestRunResult
from adapters.nautilus.strategy import BaselineSmaStrategy, DomainStrategy, StrategyContext

__all__ = [
    "BacktestConfig",
    "BacktestRunResult",
    "BaselineSmaConfig",
    "BaselineSmaStrategy",
    "CommissionConfig",
    "Dataset",
    "DatasetConfig",
    "DomainStrategy",
    "NautilusBacktestRunner",
    "PortfolioMetrics",
    "RejectionConfig",
    "SlippageConfig",
    "SpreadConfig",
    "StrategyContext",
    "build_dataset",
    "code_sha",
    "compute_metrics",
    "eurusd_instrument",
    "instrument_to_nautilus",
    "order_intent_to_order",
    "report_from_order_accepted",
    "report_from_order_filled",
    "report_from_order_rejected",
    "snapshot_from_position_event",
    "trade_outcome_from_position_closed",
]
