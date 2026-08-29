"""ZeroMQ transport for the MT4 execution protocol (ADR-0020).

Private-network ZeroMQ (§34.18) — sockets are never exposed to the internet.
Topology (frozen in ``mt4/protocol/README.md``):

- command channel  Core REQ → MT4 REP  (submit/cancel/modify/reconciliation)
- event channel    MT4 PUSH → Core PULL (heartbeat/account/position/fills)
- quote channel    MT4 PUB → Core SUB   (market_quote, topic = symbol)

Connection health is derived from the heartbeat stream: CONNECTED → DEGRADED
→ DOWN. The Core refuses to send new commands once the bridge is DOWN (INV-7).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import cast

import zmq
from core.clock.clocks import Clock
from pydantic import BaseModel, ConfigDict, Field

from adapters.mt4.errors import Mt4ErrorCode, Mt4ProtocolError, ProtocolErrorDetail
from adapters.mt4.protocol import WireMessage, parse_message, serialize_message

__all__ = [
    "ConnectionHealth",
    "ConnectionMonitor",
    "Mt4Endpoints",
    "bind_ephemeral",
    "recv_frame",
    "send_frame",
]


class Mt4Endpoints(BaseModel):
    """The three ZeroMQ channel addresses.

    Defaults are private loopback. Production deployments point the command
    and event channels at the WireGuard tunnel interface of the MT4 host.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    command_addr: str = Field(default="tcp://127.0.0.1:5555", min_length=1)
    events_addr: str = Field(default="tcp://127.0.0.1:5556", min_length=1)
    quotes_addr: str = Field(default="tcp://127.0.0.1:5557", min_length=1)


class ConnectionHealth(StrEnum):
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"


class ConnectionMonitor:
    """Tracks bridge liveness from the heartbeat stream (clock-injected)."""

    def __init__(
        self,
        clock: Clock,
        *,
        degraded_after_seconds: float = 3.0,
        down_after_seconds: float = 6.0,
    ) -> None:
        if not (0 < degraded_after_seconds < down_after_seconds):
            raise ValueError("require 0 < degraded_after < down_after")
        self._clock = clock
        self._degraded_after = degraded_after_seconds
        self._down_after = down_after_seconds
        self._last_heartbeat: datetime | None = None
        self._connected_at: datetime | None = None

    def mark_connected(self, now: datetime | None = None) -> None:
        self._connected_at = now or self._clock.now()
        self._last_heartbeat = None

    def on_heartbeat(self, now: datetime | None = None) -> None:
        self._last_heartbeat = now or self._clock.now()

    def last_heartbeat_at(self) -> datetime | None:
        return self._last_heartbeat

    def state(self, now: datetime | None = None) -> ConnectionHealth:
        now = now or self._clock.now()
        reference = self._last_heartbeat or self._connected_at
        if reference is None:
            return ConnectionHealth.DOWN
        age = (now - reference).total_seconds()
        if age >= self._down_after:
            return ConnectionHealth.DOWN
        if age >= self._degraded_after:
            return ConnectionHealth.DEGRADED
        return ConnectionHealth.CONNECTED

    def block_new_commands(self, now: datetime | None = None) -> bool:
        return self.state(now) is ConnectionHealth.DOWN


def send_frame(socket: zmq.Socket[bytes], message: WireMessage) -> None:
    """Send one message with an integrity checksum attached."""
    socket.send(serialize_message(message))


def recv_frame(socket: zmq.Socket[bytes], timeout_ms: int, now: datetime) -> WireMessage:
    """Receive one message with a timeout; raise structured TIMEOUT on expiry."""
    poller = zmq.Poller()
    poller.register(socket, zmq.POLLIN)
    events = poller.poll(timeout_ms)
    if not events:
        raise Mt4ProtocolError(
            ProtocolErrorDetail.create(
                Mt4ErrorCode.TIMEOUT,
                f"no reply within {timeout_ms} ms",
                now=now,
            )
        )
    raw = socket.recv()
    message = parse_message(raw)
    message.verify_checksum()
    return message


def bind_ephemeral(socket: zmq.Socket[bytes], addr: str) -> str:
    """Bind a tcp endpoint, allowing port ``*`` to pick an ephemeral port."""
    if addr.startswith("tcp://") and ":*" in addr:
        socket.bind(addr)
        last = cast(bytes, socket.getsockopt(zmq.LAST_ENDPOINT))
        return last.decode("utf-8")
    socket.bind(addr)
    return addr
