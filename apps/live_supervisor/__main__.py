"""CLI entry point: ``python -m apps.live_supervisor <run|run-once|status>``."""

from __future__ import annotations

import argparse
import json
import sys

from core.config.settings import get_settings
from core.clock.clocks import SystemClock
from core.security import install_redacting_logging
from engines.live_auto.config import LiveAutoConfig
from engines.live_auto.persistence import PostgresLiveAutoStore
from engines.live_auto.registry import LiveAutoRegistry

from apps.live_supervisor.supervisor import run_once, serve


def _status() -> int:
    settings = get_settings()
    registry = LiveAutoRegistry(
        PostgresLiveAutoStore(settings.postgres_dsn),
        LiveAutoConfig.from_settings(settings),
        SystemClock(),
    )
    print(json.dumps(registry.status(), indent=2, default=str))
    return 0


def main(argv: list[str] | None = None) -> int:
    install_redacting_logging()
    parser = argparse.ArgumentParser(prog="apps.live_supervisor", description=__doc__)
    parser.add_argument("command", choices=["run", "run-once", "status"])
    parser.add_argument("--gate-timeout-seconds", type=int, default=120)
    args = parser.parse_args(argv)
    if args.command == "status":
        return _status()
    if args.command == "run-once":
        return run_once(timeout_seconds=args.gate_timeout_seconds)
    serve()
    return 0


if __name__ == "__main__":
    sys.exit(main())
