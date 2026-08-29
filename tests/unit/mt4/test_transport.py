"""ZeroMQ transport + connection health tests (no MetaTrader, no docker)."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

import zmq
from adapters.mt4.protocol import HeartbeatEvent, serialize_message
from adapters.mt4.transport import ConnectionHealth, ConnectionMonitor, bind_ephemeral
from core.clock.clocks import VirtualClock
from tests.unit.mt4.helpers import T0


def test_connection_monitor_transitions() -> None:
    clock = VirtualClock(T0)
    monitor = ConnectionMonitor(clock, degraded_after_seconds=3.0, down_after_seconds=6.0)
    assert monitor.state() is ConnectionHealth.DOWN  # never connected

    monitor.mark_connected()
    assert monitor.state() is ConnectionHealth.CONNECTED

    clock.advance(timedelta(seconds=4))
    assert monitor.state() is ConnectionHealth.DEGRADED

    clock.advance(timedelta(seconds=3))
    assert monitor.state() is ConnectionHealth.DOWN
    assert monitor.block_new_commands()

    monitor.on_heartbeat()
    assert monitor.state() is ConnectionHealth.CONNECTED
    assert not monitor.block_new_commands()


def test_monitor_rejects_bad_thresholds() -> None:
    import pytest

    with pytest.raises(ValueError):
        ConnectionMonitor(VirtualClock(T0), degraded_after_seconds=5.0, down_after_seconds=1.0)


def test_inproc_req_rep_roundtrip() -> None:
    """REQ/REP over inproc in one context — the command channel contract."""
    context = zmq.Context()
    rep = context.socket(zmq.REP)
    rep.setsockopt(zmq.LINGER, 0)
    address = "inproc://mt4-transport-test"
    rep.bind(address)
    req = context.socket(zmq.REQ)
    req.setsockopt(zmq.LINGER, 0)
    req.connect(address)

    heartbeat = HeartbeatEvent(
        message_id=uuid4(),
        timestamp=T0,
        sequence=1,
        broker_connected=True,
        trading_enabled=True,
    )
    req.send(serialize_message(heartbeat))

    poller = zmq.Poller()
    poller.register(rep, zmq.POLLIN)
    assert poller.poll(2000)
    request = rep.recv()
    rep.send(serialize_message(heartbeat))

    reply = req.recv()
    assert reply == request == serialize_message(heartbeat)

    rep.close()
    req.close()
    context.term()


def test_bind_ephemeral_resolves_port() -> None:
    context = zmq.Context()
    socket = context.socket(zmq.PUSH)
    socket.setsockopt(zmq.LINGER, 0)
    bound = bind_ephemeral(socket, "tcp://127.0.0.1:*")
    assert bound.startswith("tcp://127.0.0.1:")
    assert not bound.endswith("*")
    socket.close()
    context.term()
