"""Deterministic backtest CLI: prints the reproducibility fingerprints.

Usage:
    uv run python -m adapters.nautilus.cli [--seed N]

The printed JSON contains ``input_hash`` (dataset + config + code SHA) and
``output_hash`` (all domain outputs). Running the same command twice must print
identical hashes — this is the cross-process Definition-of-Done check.
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal

from adapters.nautilus.config import (
    BacktestConfig,
    BaselineSmaConfig,
    CommissionConfig,
    DatasetConfig,
    RejectionConfig,
    SlippageConfig,
    SpreadConfig,
)
from adapters.nautilus.engine import NautilusBacktestRunner, eurusd_instrument


def build_config(seed: int) -> BacktestConfig:
    return BacktestConfig(
        seed=seed,
        instrument=eurusd_instrument(),
        dataset=DatasetConfig(seed=seed, n_bars=600),
        spread=SpreadConfig(half_spread_ticks=1),
        slippage=SlippageConfig(fixed_ticks=1, random_min_ticks=0, random_max_ticks=2),
        commission=CommissionConfig(rate_bps=Decimal("0.5"), min_amount=Decimal("0")),
        rejection=RejectionConfig(probability=0.05),
        baseline=BaselineSmaConfig(fast_window=5, slow_window=20, quantity=Decimal("100000")),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic Nautilus backtest")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    config = build_config(args.seed)
    result = NautilusBacktestRunner(config).run()
    print(
        json.dumps(
            {
                "seed": args.seed,
                "instrument_id": result.instrument_id,
                "dataset_hash": result.dataset_hash,
                "config_hash": result.config_hash,
                "code_sha": result.code_sha,
                "input_hash": result.input_hash,
                "output_hash": result.output_hash,
                "n_reports": len(result.execution_reports),
                "n_trades": result.metrics.n_trades,
                "net_profit": str(result.metrics.net_profit),
                "total_commission": str(result.metrics.total_commission),
                "total_slippage": str(result.metrics.total_slippage),
                "return_pct": result.metrics.return_pct,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
