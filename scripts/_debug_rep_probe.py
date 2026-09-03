"""Debug: probe the QuantBridgeEA REP socket directly (raw frames)."""
from __future__ import annotations

import sys
from uuid import uuid4

import zmq

sys.path.insert(0, ".")
from adapters.mt4.protocol import (  # noqa: E402
    ReconciliationRequestCommand,
    parse_message,
    serialize_message,
)
from core.clock.clocks import SystemClock  # noqa: E402

ctx = zmq.Context()
sock = ctx.socket(zmq.REQ)
sock.setsockopt(zmq.LINGER, 0)
sock.setsockopt(zmq.RCVTIMEO, 8000)
sock.connect("tcp://127.0.0.1:15555")

clock = SystemClock()
cmd = ReconciliationRequestCommand(
    message_id=uuid4(),
    timestamp=clock.now(),
    sequence=1,
    strategy_id="CORE",
    strategy_version="CORE",
)
raw = serialize_message(cmd)
print("SENDING:", raw.decode("utf-8", "replace"))
sock.send(raw)
try:
    reply = sock.recv()
    print("RAW REPLY:", reply.decode("utf-8", "replace"))
    try:
        parsed = parse_message(reply)
        print("PARSED:", type(parsed).__name__)
    except Exception as exc:  # noqa: BLE001
        print("PARSE ERROR:", repr(exc))
except zmq.Again:
    print("NO REPLY within 8s (EA did not answer the REP socket)")
sock.close()
ctx.term()
