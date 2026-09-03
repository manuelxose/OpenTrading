"""Probe the QuantBridgeEA: DEMO account gate + broker connectivity.

Exit codes:
  0 — EA reachable, broker connected and the logged account is a DEMO account.
  1 — EA unreachable / timeout.
  2 — EA reachable but the account is NOT a demo (never touch live accounts).
"""
from __future__ import annotations

import sys
from uuid import uuid4

sys.path.insert(0, ".")
import zmq  # noqa: E402

from adapters.mt4.protocol import (  # noqa: E402
    Mt4MessageType,
    ReconciliationRequestCommand,
    ReconciliationResponse,
    parse_message,
    serialize_message,
)
from core.clock.clocks import SystemClock  # noqa: E402


def main() -> int:
    addr = sys.argv[1] if len(sys.argv) > 1 else "tcp://127.0.0.1:15555"
    timeout_s = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
    clock = SystemClock()
    ctx = zmq.Context()
    sock = ctx.socket(zmq.REQ)
    sock.setsockopt(zmq.LINGER, 0)
    sock.setsockopt(zmq.RCVTIMEO, int(timeout_s * 1000))
    sock.connect(addr)
    try:
        cmd = ReconciliationRequestCommand(
            message_id=uuid4(),
            timestamp=clock.now(),
            sequence=1,
            strategy_id="CORE",
            strategy_version="CORE",
        )
        sock.send(serialize_message(cmd))
        try:
            raw = sock.recv()
        except zmq.Again:
            print("no reply from the EA (timeout)")
            return 1
        reply = parse_message(raw)
        if reply.message_type is not Mt4MessageType.RECONCILIATION_RESPONSE:
            print(f"unexpected reply type: {reply.message_type}")
            return 1
        assert isinstance(reply, ReconciliationResponse)
        print(
            f"account={reply.account.account_id} is_demo={reply.account.is_demo} "
            f"broker_connected={reply.broker_connected} "
            f"trading_enabled={reply.trading_enabled} positions={len(reply.positions)}"
        )
        if not reply.broker_connected:
            return 1
        if not reply.account.is_demo:
            print("REFUSED: the terminal is on a non-demo account (demo-first policy).")
            return 2
        return 0
    finally:
        sock.close()
        ctx.term()


if __name__ == "__main__":
    raise SystemExit(main())
