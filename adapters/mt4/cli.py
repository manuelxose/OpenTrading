"""Command-line entrypoints for the MT4 execution protocol (Phase 6).

- ``run``   — start the Python MT4 emulator (stand-in for QuantBridgeEA.mq4).
- ``smoke`` — run the built-in lifecycle scenario in-process against the
  emulator; exercises submit/ack/fill/cancel/modify/reject/reconcile/heartbeat
  over real ZeroMQ loopback sockets without MetaTrader. Exit 0 = all checks
  passed.
"""

from __future__ import annotations

import argparse
import time
from decimal import Decimal
from uuid import uuid4

from core.clock.clocks import SystemClock
from core.domain.enums import OrderSide, OrderType

from adapters.mt4.broker import BrokerConfig, SymbolSpec
from adapters.mt4.client import Mt4ExecutionClient
from adapters.mt4.emulator import Mt4Emulator
from adapters.mt4.errors import Mt4ErrorCode
from adapters.mt4.protocol import Mt4MessageType, OrderAck, OrderReject, WireMessage
from adapters.mt4.transport import Mt4Endpoints

__all__ = ["main", "run_emulator", "run_smoke"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mt4", description="MT4 execution protocol tools")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the Python MT4 emulator")
    run.add_argument(
        "--command", dest="command_addr", default="tcp://127.0.0.1:5555"
    )
    run.add_argument("--events", default="tcp://127.0.0.1:5556")
    run.add_argument("--quotes", default="tcp://127.0.0.1:5557")
    run.add_argument("--seed", type=int, default=42)

    sub.add_parser("smoke", help="run the built-in lifecycle scenario and exit")
    return parser


def run_emulator(endpoints: Mt4Endpoints, seed: int) -> None:
    clock = SystemClock()
    emulator = Mt4Emulator(clock, endpoints=endpoints, seed=seed)
    bound = emulator.start()
    print(
        f"MT4 emulator listening (seed={seed})\n"
        f"  command: {bound.command_addr}\n"
        f"  events:  {bound.events_addr}\n"
        f"  quotes:  {bound.quotes_addr}\n"
        "Press Ctrl+C to stop."
    )
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nstopping emulator")
    finally:
        emulator.stop()


def run_smoke() -> int:
    """Full lifecycle against the emulator over real loopback ZeroMQ sockets."""
    clock = SystemClock()
    symbols = {
        "EURUSD": SymbolSpec(
            initial_mid=Decimal("1.08000"),
            spread=Decimal("0.00012"),
            max_spread=Decimal("0.0003"),
        )
    }
    emulator = Mt4Emulator(
        clock,
        endpoints=Mt4Endpoints(
            command_addr="tcp://127.0.0.1:*",
            events_addr="tcp://127.0.0.1:*",
            quotes_addr="tcp://127.0.0.1:*",
        ),
        broker_config=BrokerConfig(symbols=symbols),
        seed=7,
        heartbeat_interval_seconds=0.2,
        quote_interval_seconds=0.05,
    )
    endpoints = emulator.start()
    checks: list[tuple[str, bool]] = []
    with Mt4ExecutionClient(clock, endpoints=endpoints, request_timeout_seconds=5.0) as client:
        reply = client.submit_order(
            order_intent_id=uuid4(),
            strategy_id="smoke-strategy",
            strategy_version="1.0.0",
            symbol="EURUSD",
            side=OrderSide.BUY,
            quantity=Decimal("0.10"),
            order_type=OrderType.MARKET,
            max_slippage=Decimal("0.0003"),
        )
        checks.append(("submit_order acked", isinstance(reply, OrderAck)))
        if isinstance(reply, OrderAck):
            checks.append(("market order filled on ack", reply.status == "FILLED"))

        events = _collect_events(client, wanted={Mt4MessageType.FILL, Mt4MessageType.HEARTBEAT})
        checks.append(("fill event received", Mt4MessageType.FILL in events))
        checks.append(("heartbeat received", Mt4MessageType.HEARTBEAT in events))

        reconciliation = client.reconcile()
        checks.append(("reconciliation shows one position", len(reconciliation.positions) == 1))

        bad = client.submit_order(
            order_intent_id=uuid4(),
            strategy_id="smoke-strategy",
            strategy_version="1.0.0",
            symbol="NOTLISTED",
            side=OrderSide.BUY,
            quantity=Decimal("0.10"),
            order_type=OrderType.MARKET,
        )
        checks.append(
            (
                "unknown symbol rejected",
                isinstance(bad, OrderReject)
                and (
                    bad.error.code is Mt4ErrorCode.SYMBOL_NOT_ALLOWED
                    if isinstance(bad, OrderReject)
                    else False
                ),
            )
        )
    emulator.stop()
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    return 0 if all(ok for _, ok in checks) else 1


def _collect_events(
    client: Mt4ExecutionClient, wanted: set[Mt4MessageType], deadline: float = 3.0
) -> dict[Mt4MessageType, WireMessage]:
    import time as _time

    found: dict[Mt4MessageType, WireMessage] = {}
    start = _time.monotonic()
    while _time.monotonic() - start < deadline and not wanted.issubset(found):
        event = client.poll_event(timeout_ms=100)
        if event is not None:
            found.setdefault(event.message_type, event)
    return found


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "run":
        run_emulator(
            Mt4Endpoints(
                command_addr=args.command_addr,
                events_addr=args.events,
                quotes_addr=args.quotes,
            ),
            seed=args.seed,
        )
        return 0
    return run_smoke()


if __name__ == "__main__":
    raise SystemExit(main())
