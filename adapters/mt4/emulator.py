"""Python MT4 emulator — the bridge's stand-in before real MetaTrader (Phase 6).

The emulator implements the MT4 side of ADR-0020 exactly as QuantBridgeEA.mq4
will: bind ZeroMQ channels, receive commands (REP), run the command gate
(expiry → duplicates → sequence), run the EA defense-in-depth venue checks via
:class:`SimulatedBroker`, reply with order_ack/order_reject, and push
heartbeat / account / position / fill events plus market quotes.

It needs no MetaTrader, no Docker, and no network beyond loopback — this is
what lets the Core execute the full lifecycle suite (Phase 6 DoD).
"""

from __future__ import annotations

import threading
import uuid as uuid_lib
from datetime import datetime
from uuid import UUID

import zmq
from core.clock.clocks import Clock, SystemClock

from adapters.mt4.broker import BrokerConfig, SimulatedBroker
from adapters.mt4.errors import Mt4ErrorCode, Mt4ProtocolError, ProtocolErrorDetail
from adapters.mt4.guards import CommandGate
from adapters.mt4.ledger import IntentLedger
from adapters.mt4.protocol import (
    CancelOrderCommand,
    CommandMessage,
    HeartbeatEvent,
    MarketQuote,
    ModifyOrderCommand,
    OrderAck,
    OrderReject,
    ReconciliationRequestCommand,
    ReconciliationResponse,
    SubmitOrderCommand,
    WireMessage,
    parse_message,
    serialize_message,
)
from adapters.mt4.transport import Mt4Endpoints, bind_ephemeral

__all__ = ["Mt4Emulator"]


class Mt4Emulator:
    """The Python stand-in for QuantBridgeEA.mq4 + the broker.

    Serve loop runs in a daemon thread; :meth:`step_once` exposes a single
    iteration for deterministic tests.
    """

    def __init__(
        self,
        clock: Clock | None = None,
        broker: SimulatedBroker | None = None,
        endpoints: Mt4Endpoints | None = None,
        *,
        broker_config: BrokerConfig | None = None,
        seed: int = 42,
        heartbeat_interval_seconds: float = 1.0,
        quote_interval_seconds: float = 0.1,
    ) -> None:
        self._clock = clock or SystemClock()
        self._endpoints = endpoints or Mt4Endpoints()
        self._broker = broker or SimulatedBroker(
            self._clock, broker_config or BrokerConfig(), seed=seed
        )
        self._gate = CommandGate(self._clock)
        self._seed = seed
        self._heartbeat_interval = heartbeat_interval_seconds
        self._quote_interval = quote_interval_seconds
        self._emulator_id = UUID(int=seed & 0xFFFFFFFFFFFFFFFF)
        self._ctx: zmq.Context[zmq.Socket[bytes]] | None = None
        self._control: zmq.Socket[bytes] | None = None
        self._events: zmq.Socket[bytes] | None = None
        self._quotes: zmq.Socket[bytes] | None = None
        self._event_seq = 0
        self._reply_seq = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_heartbeat = self._clock.now()
        self._last_quote_step = self._clock.now()
        self.safe_mode = False
        self.broker_connected = True
        self._bound_endpoints = endpoints or Mt4Endpoints()

    # ── Lifecycle ─────────────────────────────────────────────────────────
    def start(self, *, serve_in_thread: bool = True) -> Mt4Endpoints:
        """Bind channels and (optionally) start the serve thread.

        Returns the actually bound endpoints (useful when ports were ``*``).
        """
        if self._ctx is not None:
            raise RuntimeError("emulator already started")
        self._stop = threading.Event()  # clear a previous stop() (restart support)
        self._ctx = zmq.Context()
        self._control = self._ctx.socket(zmq.REP)
        self._control.setsockopt(zmq.LINGER, 0)
        self._control.setsockopt(zmq.SNDTIMEO, 1000)
        self._events = self._ctx.socket(zmq.PUSH)
        self._events.setsockopt(zmq.LINGER, 0)
        self._events.setsockopt(zmq.SNDTIMEO, 500)
        self._quotes = self._ctx.socket(zmq.PUB)
        self._quotes.setsockopt(zmq.LINGER, 0)
        self._quotes.setsockopt(zmq.SNDTIMEO, 500)
        command_addr = bind_ephemeral(self._control, self._endpoints.command_addr)
        events_addr = bind_ephemeral(self._events, self._endpoints.events_addr)
        quotes_addr = bind_ephemeral(self._quotes, self._endpoints.quotes_addr)
        self._bound_endpoints = Mt4Endpoints(
            command_addr=command_addr,
            events_addr=events_addr,
            quotes_addr=quotes_addr,
        )
        if serve_in_thread:
            self._thread = threading.Thread(target=self._serve, name="mt4-emulator", daemon=True)
            self._thread.start()
        return self._bound_endpoints

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        for socket in (self._control, self._events, self._quotes):
            if socket is not None:
                socket.close()
        if self._ctx is not None:
            self._ctx.term()
        self._ctx = None
        self._control = self._events = self._quotes = None

    def __enter__(self) -> Mt4Emulator:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    @property
    def endpoints(self) -> Mt4Endpoints:
        return self._bound_endpoints

    @property
    def broker(self) -> SimulatedBroker:
        return self._broker

    @property
    def ledger(self) -> IntentLedger:
        return self._gate.ledger

    # ── Serve loop ────────────────────────────────────────────────────────
    def _serve(self) -> None:
        try:
            while not self._stop.is_set():
                self.step_once(timeout_ms=50)
        except (zmq.ZMQError, zmq.ContextTerminated):  # teardown race — exit quietly
            return

    def step_once(self, timeout_ms: int = 50) -> None:
        """One serve iteration: handle a command (if any) + periodic work."""
        assert self._control is not None
        now = self._clock.now()

        poller = zmq.Poller()
        poller.register(self._control, zmq.POLLIN)
        events = poller.poll(timeout_ms)
        for socket, _ in events:
            if socket is self._control:
                raw = self._control.recv()
                self._control.send(self._handle_command(raw))

        if (now - self._last_heartbeat).total_seconds() >= self._heartbeat_interval:
            self._publish_heartbeat(now)
            self._last_heartbeat = now

        if (now - self._last_quote_step).total_seconds() >= self._quote_interval:
            self._step_market(now)
            self._last_quote_step = now

    def _step_market(self, now: datetime) -> None:
        for event in self._broker.advance(now):
            self._push_event(event)
        self._publish_quotes()

    # ── Command handling (mirror of QuantBridgeEA.mq4 logic) ─────────────
    def _handle_command(self, raw: bytes) -> bytes:
        try:
            message = parse_message(raw)
        except Mt4ProtocolError as exc:
            return serialize_message(self._reject_reply(None, exc.detail))

        if not isinstance(message, CommandMessage):
            return serialize_message(
                self._reject_reply(
                    None,
                    ProtocolErrorDetail.create(
                        Mt4ErrorCode.UNKNOWN_MESSAGE_TYPE,
                        "expected a command message",
                        trace_id=message.trace_id,
                        now=message.timestamp,
                    ),
                )
            )

        try:
            message.verify_checksum()
        except Mt4ProtocolError as exc:
            return serialize_message(self._reject_reply(message, exc.detail))

        if self.safe_mode and isinstance(message, SubmitOrderCommand):
            return serialize_message(
                self._reject_reply(
                    message,
                    ProtocolErrorDetail.create(
                        Mt4ErrorCode.SAFE_MODE_ACTIVE,
                        "reconciliation divergence — new entries blocked (INV-6)",
                        trace_id=message.trace_id,
                        order_intent_id=message.order_intent_id,
                        now=self._clock.now(),
                    ),
                )
            )

        outcome = self._gate.evaluate(message)
        if outcome.replay is not None:
            duplicate = isinstance(outcome.replay, OrderAck)
            return serialize_message(
                self._reframe_reply(message, outcome.replay, duplicate=duplicate)
            )
        if outcome.error is not None:
            return serialize_message(self._reject_reply(message, outcome.error))

        reply, pushed_events = self._dispatch(message)
        self._gate.record(message, reply)
        for event in pushed_events:
            self._push_event(event)
        return serialize_message(self._reframe_reply(message, reply))

    def _dispatch(self, message: CommandMessage) -> tuple[WireMessage, list[WireMessage]]:
        now = self._clock.now()
        if isinstance(message, SubmitOrderCommand):
            result = self._broker.process_submit(message, now)
        elif isinstance(message, CancelOrderCommand):
            result = self._broker.process_cancel(message, now)
        elif isinstance(message, ModifyOrderCommand):
            result = self._broker.process_modify(message, now)
        elif isinstance(message, ReconciliationRequestCommand):
            response: WireMessage = ReconciliationResponse(
                message_id=UUID(int=0),
                timestamp=now,
                sequence=0,
                account=self._broker.account_state(now),
                positions=self._broker.positions(now),
                open_order_intent_ids=self._broker.open_order_intent_ids(),
                last_sequences=self._gate.sequences_snapshot(),
                broker_connected=self.broker_connected,
                trading_enabled=self._broker.trading_enabled,
            )
            return response, []
        else:  # pragma: no cover - registry guards this
            raise Mt4ProtocolError(
                ProtocolErrorDetail.create(
                    Mt4ErrorCode.UNKNOWN_MESSAGE_TYPE,
                    f"no dispatch for {message.message_type.value}",
                    now=now,
                )
            )

        if result.reject is not None:
            reply: WireMessage = self._reject_reply(message, result.reject)
            return reply, []
        assert result.ack is not None
        return result.ack, result.events

    # ── Framing helpers ───────────────────────────────────────────────────
    def _reframe_reply(
        self, command: CommandMessage, reply: WireMessage, *, duplicate: bool = False
    ) -> WireMessage:
        update: dict[str, object] = {
            "message_id": uuid_lib.uuid5(command.message_id, reply.message_type.value),
            "correlation_id": command.message_id,
            "timestamp": self._clock.now(),
            "sequence": command.sequence,
            "checksum": None,
        }
        if isinstance(reply, OrderAck):
            update["duplicate"] = duplicate
        return reply.model_copy(update=update)

    def _reject_reply(
        self, command: CommandMessage | None, error: ProtocolErrorDetail
    ) -> OrderReject:
        self._reply_seq += 1
        message_id = (
            uuid_lib.uuid5(command.message_id, f"reject-{self._reply_seq}")
            if command is not None
            else uuid_lib.uuid5(self._emulator_id, f"reject-{self._reply_seq}")
        )
        return OrderReject(
            message_id=message_id,
            trace_id=command.trace_id if command is not None else None,
            timestamp=self._clock.now(),
            sequence=command.sequence if command is not None else 0,
            correlation_id=command.message_id if command is not None else None,
            order_intent_id=command.order_intent_id if command is not None else None,
            error=error,
        )

    def _push_event(self, event: WireMessage) -> None:
        if self._events is None:
            return
        self._event_seq += 1
        framed = event.model_copy(
            update={
                "message_id": uuid_lib.uuid5(self._emulator_id, f"event-{self._event_seq}"),
                "sequence": self._event_seq,
                "correlation_id": None,
                "checksum": None,
            }
        )
        try:
            self._events.send(serialize_message(framed))
        except (zmq.Again, zmq.ZMQError):
            return  # downstream not draining — drop this event, keep serving

    def _publish_heartbeat(self, now: datetime) -> None:
        heartbeat = HeartbeatEvent(
            message_id=UUID(int=0),
            timestamp=now,
            sequence=0,
            broker_connected=self.broker_connected,
            trading_enabled=self._broker.trading_enabled,
        )
        self._push_event(heartbeat)

    def _publish_quotes(self) -> None:
        if self._quotes is None:
            return
        for symbol in self._broker.symbols():
            bid = self._broker.bid(symbol)
            ask = self._broker.ask(symbol)
            quote = MarketQuote(
                message_id=uuid_lib.uuid5(self._emulator_id, f"quote-{symbol}-{bid}-{ask}"),
                timestamp=self._clock.now(),
                sequence=self._event_seq,
                symbol=symbol,
                bid=bid,
                ask=ask,
                spread=ask - bid,
                tradable=self._broker.trading_enabled,
            )
            try:
                self._quotes.send_multipart([symbol.encode("utf-8"), serialize_message(quote)])
            except (zmq.Again, zmq.ZMQError):
                return
