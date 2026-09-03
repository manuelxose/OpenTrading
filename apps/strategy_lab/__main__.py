"""CLI entry point: ``python -m apps.strategy_lab improve``."""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal

from core.config.settings import get_settings
from core.security import install_redacting_logging

from apps.strategy_lab.lab import ScalpingGrid, run_lab


def main(argv: list[str] | None = None) -> int:
    install_redacting_logging()
    parser = argparse.ArgumentParser(prog="apps.strategy_lab", description=__doc__)
    parser.add_argument("command", choices=["improve"])
    parser.add_argument("--strategy-id", default="scalping-ema-live-001")
    parser.add_argument("--instrument", default="BTCUSD")
    parser.add_argument("--spread", type=Decimal, default=Decimal("5.0"))
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args(argv)
    settings = get_settings()
    run_lab(
        settings,
        strategy_id=args.strategy_id,
        instrument_id=args.instrument,
        spread=args.spread,
        grid=ScalpingGrid.aggressive(),
        top=args.top,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
