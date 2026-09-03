"""Wait for the first bridge heartbeat on the events channel (orchestrator helper).

Usage: python _wait_bridge_heartbeat.py <events_addr> [timeout_seconds]

Exits 0 once a heartbeat event arrives, 1 on timeout. Used by
run-mt4-bridge.ps1 to guarantee the bridge serve loop is up before the
first REQ is sent (avoiding REP lockstep races).
"""

import sys
import time

import zmq

from adapters.mt4.protocol import Mt4MessageType, parse_message


def main() -> int:
    addr = sys.argv[1]
    timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0
    ctx = zmq.Context()
    sock = ctx.socket(zmq.PULL)
    sock.setsockopt(zmq.LINGER, 0)
    sock.connect(addr)
    poller = zmq.Poller()
    poller.register(sock, zmq.POLLIN)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if poller.poll(200):
            raw = sock.recv()
            message = parse_message(raw)
            print(f"bridge event: {message.message_type.value}")
            if message.message_type is Mt4MessageType.HEARTBEAT:
                sock.close()
                ctx.term()
                return 0
    sock.close()
    ctx.term()
    print("no heartbeat within timeout")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
