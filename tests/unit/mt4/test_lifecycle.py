"""Phase 6 DoD lifecycle: the Core executes the full MT4 lifecycle against the
Python emulator over real ZeroMQ sockets — no MetaTrader required."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from adapters.mt4.broker import BrokerConfig, SymbolSpec
from adapters.mt4.client import Mt4ExecutionClient
from adapters.mt4.emulator import Mt4Emulator
from adapters.mt4.errors import Mt4ErrorCode, Mt4ProtocolError
from adapters.mt4.protocol import FillEvent, Mt4MessageType, OrderAck, OrderReject, WireMessage
from adapters.mt4.transport import ConnectionHealth, Mt4Endpoints
from core.clock.clocks import SystemClock
from core.domain.enums import OrderSide, OrderType
from tests.unit.mt4.helpers import make_submit

EURUSD = SymbolSpec(
    initial_mid=Decimal("1.08000"),
    spread=Decimal("0.00012"),
    max_spread=Decimal("0.0003"),
)


def _collect(
    client: Mt4ExecutionClient,
    predicate: Callable[[WireMessage], bool],
    *,
    deadline_seconds: float = 5.0,
    poll_ms: int = 50,
) -> list[WireMessage]:
    """Collect pushed events until ``predicate`` holds or the deadline passes."""
    found: list[WireMessage] = []
    start = time.monotonic()
    while time.monotonic() - start < deadline_seconds:
        found.extend(client.drain_events(timeout_ms=poll_ms))
        if any(predicate(event) for event in found):
            break
    return found


def _wait_heartbeat(client: Mt4ExecutionClient) -> None:
    _collect(client, lambda e: e.message_type is Mt4MessageType.HEARTBEAT)


@pytest.fixture()
def stack() -> Iterator[tuple[Mt4Emulator, Mt4ExecutionClient]]:
    """Emulator + client on ephemeral loopback endpoints."""
    clock = SystemClock()
    emulator = Mt4Emulator(
        clock,
        endpoints=Mt4Endpoints(
            command_addr="tcp://127.0.0.1:*",
            events_addr="tcp://127.0.0.1:*",
            quotes_addr="tcp://127.0.0.1:*",
        ),
        broker_config=BrokerConfig(symbols={"EURUSD": EURUSD}),
        seed=7,
        heartbeat_interval_seconds=0.1,
        quote_interval_seconds=0.05,
    )
    endpoints = emulator.start()
    client = Mt4ExecutionClient(
        clock,
        endpoints=endpoints,
        request_timeout_seconds=5.0,
        degraded_after_seconds=0.6,
        down_after_seconds=1.2,
    )
    client.connect()
    yield emulator, client
    client.close()
    emulator.stop()


def test_full_lifecycle_without_metatrader(
    stack: tuple[Mt4Emulator, Mt4ExecutionClient],
) -> None:
    _emulator, client = stack

    # Heartbeat → connection health CONNECTED.
    _wait_heartbeat(client)
    assert client.connection_health() is ConnectionHealth.CONNECTED

    # Submit a market order → ack + fill.
    intent = uuid4()
    reply = client.submit_order(
        order_intent_id=intent,
        strategy_id="life-strategy",
        strategy_version="1.0.0",
        symbol="EURUSD",
        side=OrderSide.BUY,
        quantity=Decimal("0.10"),
        order_type=OrderType.MARKET,
        max_slippage=Decimal("0.0003"),
    )
    assert isinstance(reply, OrderAck)
    assert reply.status == "FILLED"
    fills = _collect(client, lambda e: isinstance(e, FillEvent))
    assert len([e for e in fills if isinstance(e, FillEvent)]) == 1

    # Reconciliation reflects the broker state.
    reconciliation = client.reconcile()
    assert reconciliation.broker_connected
    assert reconciliation.trading_enabled
    assert len(reconciliation.positions) == 1
    assert reconciliation.positions[0].position.quantity == Decimal("0.10")

    # Rejection path: symbol not on the EA whitelist.
    reject = client.submit_order(
        order_intent_id=uuid4(),
        strategy_id="life-strategy",
        strategy_version="1.0.0",
        symbol="BTCUSD",
        side=OrderSide.BUY,
        quantity=Decimal("0.10"),
        order_type=OrderType.MARKET,
    )
    assert isinstance(reject, OrderReject)
    assert reject.error.code is Mt4ErrorCode.SYMBOL_NOT_ALLOWED

    # Cancel/modify path on a resting LIMIT order.
    resting_intent = uuid4()
    resting = client.submit_order(
        order_intent_id=resting_intent,
        strategy_id="life-strategy",
        strategy_version="1.0.0",
        symbol="EURUSD",
        side=OrderSide.BUY,
        quantity=Decimal("0.10"),
        order_type=OrderType.LIMIT,
        price=Decimal("1.05000"),
    )
    assert isinstance(resting, OrderAck)
    assert resting.status == "SUBMITTED"

    modified = client.modify_order(
        order_intent_id=resting_intent,
        strategy_id="life-strategy",
        strategy_version="1.0.0",
        symbol="EURUSD",
        side=OrderSide.BUY,
        quantity=Decimal("0.10"),
        order_type=OrderType.LIMIT,
        new_stop_loss=Decimal("1.04900"),
    )
    assert isinstance(modified, OrderAck)
    assert modified.status == "MODIFIED"

    cancelled = client.cancel_order(
        order_intent_id=resting_intent,
        strategy_id="life-strategy",
        strategy_version="1.0.0",
        symbol="EURUSD",
        side=OrderSide.BUY,
        quantity=Decimal("0.10"),
        order_type=OrderType.LIMIT,
    )
    assert isinstance(cancelled, OrderAck)
    assert cancelled.status == "CANCELLED"

    # Market quotes flow over the PUB/SUB channel.
    quote_seen = False
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and not quote_seen:
        quote = client.poll_quote(timeout_ms=100)
        quote_seen = quote is not None and quote[0] == "EURUSD"
    assert quote_seen


def test_same_intent_100_times_produces_one_trade(
    stack: tuple[Mt4Emulator, Mt4ExecutionClient],
) -> None:
    """The literal Phase 6 DoD, end-to-end over ZeroMQ."""
    emulator, client = stack
    _wait_heartbeat(client)

    command = make_submit(
        strategy_id="dup-strategy",
        symbol="EURUSD",
        timestamp=emulator.broker.account_state().as_of,
    )
    replies = [client.send_command(command) for _ in range(100)]

    acks = [r for r in replies if isinstance(r, OrderAck)]
    assert len(acks) == 100
    assert acks[0].duplicate is False
    assert all(a.duplicate is True for a in acks[1:])

    reconciliation = client.reconcile()
    assert len(reconciliation.positions) == 1
    assert reconciliation.positions[0].position.quantity == Decimal("0.10")

    fills = _collect(client, lambda e: isinstance(e, FillEvent))
    assert len([e for e in fills if isinstance(e, FillEvent)]) == 1


def test_conflicting_intent_rejected(
    stack: tuple[Mt4Emulator, Mt4ExecutionClient],
) -> None:
    emulator, client = stack
    _wait_heartbeat(client)

    first = make_submit(
        strategy_id="conflict-strategy",
        symbol="EURUSD",
        timestamp=emulator.broker.account_state().as_of,
    )
    ack = client.send_command(first)
    assert isinstance(ack, OrderAck)

    conflicting = first.model_copy(update={"quantity": Decimal("0.99")})
    reject = client.send_command(conflicting)
    assert isinstance(reject, OrderReject)
    assert reject.error.code is Mt4ErrorCode.INTENT_CONFLICT


def test_expired_command_rejected(
    stack: tuple[Mt4Emulator, Mt4ExecutionClient],
) -> None:
    emulator, client = stack
    _wait_heartbeat(client)

    now = emulator.broker.account_state().as_of
    expired = make_submit(
        strategy_id="expiry-strategy",
        symbol="EURUSD",
        timestamp=now - timedelta(minutes=5),
        expires_in_seconds=60,
    )
    reject = client.send_command(expired)
    assert isinstance(reject, OrderReject)
    assert reject.error.code is Mt4ErrorCode.COMMAND_EXPIRED


def test_sequence_gap_rejected(
    stack: tuple[Mt4Emulator, Mt4ExecutionClient],
) -> None:
    emulator, client = stack
    _wait_heartbeat(client)

    now = emulator.broker.account_state().as_of
    first = make_submit(strategy_id="gap-strategy", symbol="EURUSD", sequence=1, timestamp=now)
    assert isinstance(client.send_command(first), OrderAck)

    gap = make_submit(strategy_id="gap-strategy", symbol="EURUSD", sequence=7, timestamp=now)
    reject = client.send_command(gap)
    assert isinstance(reject, OrderReject)
    assert reject.error.code is Mt4ErrorCode.SEQUENCE_VIOLATION


def test_safe_mode_blocks_new_entries(
    stack: tuple[Mt4Emulator, Mt4ExecutionClient],
) -> None:
    emulator, client = stack
    _wait_heartbeat(client)

    emulator.safe_mode = True
    reject = client.submit_order(
        order_intent_id=uuid4(),
        strategy_id="safe-mode-strategy",
        strategy_version="1.0.0",
        symbol="EURUSD",
        side=OrderSide.BUY,
        quantity=Decimal("0.10"),
        order_type=OrderType.MARKET,
    )
    assert isinstance(reject, OrderReject)
    assert reject.error.code is Mt4ErrorCode.SAFE_MODE_ACTIVE
    emulator.safe_mode = False


def test_disconnect_and_restart_reconciles_and_resyncs(
    stack: tuple[Mt4Emulator, Mt4ExecutionClient],
) -> None:
    """Restart flow (§9): fresh client reconciles broker state + resyncs sequences."""
    emulator, client = stack
    _wait_heartbeat(client)

    reply = client.submit_order(
        order_intent_id=uuid4(),
        strategy_id="restart-strategy",
        strategy_version="1.0.0",
        symbol="EURUSD",
        side=OrderSide.SELL,
        quantity=Decimal("0.10"),
        order_type=OrderType.MARKET,
    )
    assert isinstance(reply, OrderAck)

    # Simulate process restart: close both sides and start over.
    client.close()
    emulator.stop()
    endpoints = emulator.start()

    fresh = Mt4ExecutionClient(
        SystemClock(),
        endpoints=endpoints,
        request_timeout_seconds=5.0,
        degraded_after_seconds=0.6,
        down_after_seconds=1.2,
    )
    fresh.connect()
    _wait_heartbeat(fresh)
    reconciliation = fresh.reconcile()
    assert len(reconciliation.positions) == 1
    assert reconciliation.positions[0].position.side.value == "SHORT"
    assert reconciliation.last_sequences.get("restart-strategy") == 1

    # Resync to the bridge's sequence state, then continue the same strategy.
    fresh.resync_sequences(reconciliation.last_sequences)
    second = fresh.submit_order(
        order_intent_id=uuid4(),
        strategy_id="restart-strategy",
        strategy_version="1.0.0",
        symbol="EURUSD",
        side=OrderSide.BUY,
        quantity=Decimal("0.10"),
        order_type=OrderType.MARKET,
    )
    assert isinstance(second, OrderAck)  # sequence 2 accepted, not a violation
    fresh.close()


def test_heartbeat_loss_blocks_new_commands(
    stack: tuple[Mt4Emulator, Mt4ExecutionClient],
) -> None:
    """INV-7: heartbeat loss → new commands blocked with NOT_CONNECTED."""
    emulator, client = stack
    _wait_heartbeat(client)

    emulator.stop()
    time.sleep(1.4)  # exceeds the fixture's down_after_seconds (1.2)
    assert client.connection_health() is ConnectionHealth.DOWN
    with pytest.raises(Mt4ProtocolError) as exc:
        client.submit_order(
            order_intent_id=uuid4(),
            strategy_id="down-strategy",
            strategy_version="1.0.0",
            symbol="EURUSD",
            side=OrderSide.BUY,
            quantity=Decimal("0.10"),
            order_type=OrderType.MARKET,
        )
    assert exc.value.code is Mt4ErrorCode.NOT_CONNECTED
