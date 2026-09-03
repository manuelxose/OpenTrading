"""Core-side MT4 execution client (Phase 6, ADR-0020).

The client is the Core's single door to the MT4 bridge: it builds commands,
enforces client-side guards (connection health, expiry), tracks per-strategy
sequences, and turns wire replies/events back into typed objects.

Transport failures raise :class:`Mt4ProtocolError` with structured codes;
venue rejections come back as :class:`OrderReject` replies (never exceptions)
so callers can branch on ``error.code``.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import zmq
from core.clock.clocks import Clock, SystemClock
from core.domain.enums import OperatingMode, OrderSide, OrderType, TimeInForce
from core.observability.metrics import OperationalMetrics, metrics
from core.schemas.trading import OrderIntent

from adapters.mt4.errors import Mt4ErrorCode, Mt4ProtocolError, ProtocolErrorDetail
from adapters.mt4.protocol import (
    CancelOrderCommand,
    CommandMessage,
    MarketQuote,
    ModifyOrderCommand,
    Mt4MessageType,
    OrderAck,
    OrderReject,
    ReconciliationRequestCommand,
    ReconciliationResponse,
    SubmitOrderCommand,
    WireMessage,
    parse_message,
    serialize_message,
)
from adapters.mt4.transport import ConnectionHealth, ConnectionMonitor, Mt4Endpoints, recv_frame

__all__ = ["Mt4ExecutionClient"]


class Mt4ExecutionClient:
    """Synchronous REQ/PULL/SUB client for the MT4 bridge.

    One client per process. Not thread-safe for concurrent commands; the REQ
    socket is strictly lock-step by design.
    """

    def __init__(
        self,
        clock: Clock | None = None,
        endpoints: Mt4Endpoints | None = None,
        *,
        request_timeout_seconds: float = 5.0,
        degraded_after_seconds: float = 3.0,
        down_after_seconds: float = 6.0,
        operational_metrics: OperationalMetrics | None = None,
        operating_mode: OperatingMode = OperatingMode.PAPER,
        live_authorizer: Callable[[OrderIntent], None] | None = None,
        # In live modes, order mutations (cancel/modify) are also fail-closed:
        # they require this deterministic authorizer (emergency policy + a
        # matching live order) or the command is refused before touching the
        # socket (ADR-0025, INV-1).
        live_mutation_authorizer: Callable[[CommandMessage], None] | None = None,
    ) -> None:
        if operating_mode is OperatingMode.LIVE_GATED and live_authorizer is None:
            raise ValueError("LIVE_GATED MT4 client requires a live approval authorizer")
        if operating_mode is OperatingMode.LIVE_AUTO and live_authorizer is None:
            raise ValueError("LIVE_AUTO MT4 client requires a live order authorizer")
        self._clock = clock or SystemClock()
        self._endpoints = endpoints or Mt4Endpoints()
        self._request_timeout_ms = int(request_timeout_seconds * 1000)
        self._monitor = ConnectionMonitor(
            self._clock,
            degraded_after_seconds=degraded_after_seconds,
            down_after_seconds=down_after_seconds,
        )
        self._ctx: zmq.Context[zmq.Socket[bytes]] | None = None
        self._command: zmq.Socket[bytes] | None = None
        self._events: zmq.Socket[bytes] | None = None
        self._quotes: zmq.Socket[bytes] | None = None
        self._sequences: dict[str, int] = {}
        self._metrics = operational_metrics or metrics
        self._operating_mode = operating_mode
        self._live_authorizer = live_authorizer
        self._live_mutation_authorizer = live_mutation_authorizer

    # ── Lifecycle ─────────────────────────────────────────────────────────
    def connect(self) -> None:
        if self._ctx is not None:
            raise RuntimeError("client already connected")
        self._ctx = zmq.Context()
        self._command = self._ctx.socket(zmq.REQ)
        self._command.setsockopt(zmq.LINGER, 0)
        self._command.connect(self._endpoints.command_addr)
        self._events = self._ctx.socket(zmq.PULL)
        self._events.setsockopt(zmq.LINGER, 0)
        self._events.connect(self._endpoints.events_addr)
        self._quotes = self._ctx.socket(zmq.SUB)
        self._quotes.setsockopt(zmq.LINGER, 0)
        self._quotes.setsockopt(zmq.SUBSCRIBE, b"")
        self._quotes.connect(self._endpoints.quotes_addr)
        self._monitor.mark_connected()

    def close(self) -> None:
        for socket in (self._command, self._events, self._quotes):
            if socket is not None:
                socket.close()
        if self._ctx is not None:
            self._ctx.term()
        self._ctx = None
        self._command = self._events = self._quotes = None

    def __enter__(self) -> Mt4ExecutionClient:
        self.connect()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def connected(self) -> bool:
        return self._ctx is not None

    def connection_health(self) -> ConnectionHealth:
        now = self._clock.now()
        heartbeat = self._monitor.last_heartbeat_at()
        if heartbeat is not None:
            self._metrics.set_mt4_heartbeat_age((now - heartbeat).total_seconds())
        return self._monitor.state(now)

    # ── Command builders (Core convenience API) ───────────────────────────
    def submit_order(
        self,
        *,
        order_intent_id: UUID,
        strategy_id: str,
        strategy_version: str,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        order_type: OrderType,
        price: Decimal | None = None,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
        max_slippage: Decimal = Decimal("0"),
        time_in_force: TimeInForce = TimeInForce.GTC,
        expires_at: datetime | None = None,
        trace_id: UUID | None = None,
        live_intent: OrderIntent | None = None,
    ) -> OrderAck | OrderReject:
        if self._operating_mode in (OperatingMode.LIVE_GATED, OperatingMode.LIVE_AUTO):
            if self._live_authorizer is None:  # constructor guarantees this
                raise self._internal(
                    f"{self._operating_mode.value} live order authorizer is unavailable"
                )
            if live_intent is None:
                raise self._internal(
                    f"{self._operating_mode.value} submission requires the authorized OrderIntent"
                )
            if (
                live_intent.order_intent_id != order_intent_id
                or live_intent.strategy_id != strategy_id
                or live_intent.strategy_version != strategy_version
                or live_intent.instrument_id != symbol
                or live_intent.side is not side
                or live_intent.quantity != quantity
                or live_intent.order_type is not order_type
                or live_intent.price != price
                or live_intent.stop_loss != stop_loss
                or live_intent.take_profit != take_profit
                or live_intent.max_slippage != max_slippage
                or live_intent.time_in_force is not time_in_force
            ):
                raise self._internal("MT4 command fields differ from approved OrderIntent")
            self._live_authorizer(live_intent)
        command = SubmitOrderCommand(
            message_id=uuid4(),
            trace_id=trace_id,
            timestamp=self._clock.now(),
            sequence=self._next_sequence(strategy_id),
            order_intent_id=order_intent_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            expires_at=expires_at or self._clock.now() + timedelta(seconds=30),
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            price=price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            max_slippage=max_slippage,
            time_in_force=time_in_force,
        )
        reply = self.send_command(command)
        if not isinstance(reply, (OrderAck, OrderReject)):
            raise self._internal(f"unexpected reply type {type(reply).__name__}")
        return reply

    def cancel_order(
        self,
        *,
        order_intent_id: UUID,
        strategy_id: str,
        strategy_version: str,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        order_type: OrderType,
        reason: str | None = None,
        trace_id: UUID | None = None,
    ) -> OrderAck | OrderReject:
        command = CancelOrderCommand(
            message_id=uuid4(),
            trace_id=trace_id,
            timestamp=self._clock.now(),
            sequence=self._next_sequence(strategy_id),
            order_intent_id=order_intent_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            expires_at=self._clock.now() + timedelta(seconds=30),
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            reason=reason,
        )
        self._assert_mutation_authorized(command)
        reply = self.send_command(command)
        if not isinstance(reply, (OrderAck, OrderReject)):
            raise self._internal(f"unexpected reply type {type(reply).__name__}")
        return reply

    def modify_order(
        self,
        *,
        order_intent_id: UUID,
        strategy_id: str,
        strategy_version: str,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        order_type: OrderType,
        new_price: Decimal | None = None,
        new_stop_loss: Decimal | None = None,
        new_take_profit: Decimal | None = None,
        trace_id: UUID | None = None,
    ) -> OrderAck | OrderReject:
        command = ModifyOrderCommand(
            message_id=uuid4(),
            trace_id=trace_id,
            timestamp=self._clock.now(),
            sequence=self._next_sequence(strategy_id),
            order_intent_id=order_intent_id,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            expires_at=self._clock.now() + timedelta(seconds=30),
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            new_price=new_price,
            new_stop_loss=new_stop_loss,
            new_take_profit=new_take_profit,
        )
        self._assert_mutation_authorized(command)
        reply = self.send_command(command)
        if not isinstance(reply, (OrderAck, OrderReject)):
            raise self._internal(f"unexpected reply type {type(reply).__name__}")
        return reply

    def reconcile(self, *, strategy_id: str = "CORE") -> ReconciliationResponse:
        command = ReconciliationRequestCommand(
            message_id=uuid4(),
            timestamp=self._clock.now(),
            sequence=self._next_sequence(strategy_id),
            strategy_id=strategy_id,
            strategy_version="CORE",
        )
        reply = self.send_command(command)
        if not isinstance(reply, ReconciliationResponse):
            raise self._internal(f"unexpected reply type {type(reply).__name__}")
        return reply

    # ── Raw command channel ───────────────────────────────────────────────
    def resync_sequences(self, mapping: dict[str, int]) -> None:
        """Adopt bridge-side last-accepted sequences after reconciliation.

        Called after a restart: without this, the fresh client would emit
        sequence 1 for a strategy the bridge already advanced (INV-6, §9).
        """
        for strategy_id, last in mapping.items():
            self._sequences[strategy_id] = max(self._sequences.get(strategy_id, 0), last)

    def send_command(self, command: CommandMessage) -> WireMessage:
        """Send one command and await its reply (idempotent-safe retries OK).

        Raises :class:`Mt4ProtocolError` on transport/timeout failures; venue
        rejections are returned as :class:`OrderReject` values.
        """
        if self._command is None:
            raise self._error(Mt4ErrorCode.NOT_CONNECTED, "client not connected")
        if self._monitor.block_new_commands():
            raise self._error(
                Mt4ErrorCode.NOT_CONNECTED,
                "bridge heartbeat lost — new commands blocked (INV-7)",
            )
        began = time.perf_counter()
        operation = command.message_type.value.lower()
        self._command.send(serialize_message(command))
        try:
            reply = recv_frame(self._command, self._request_timeout_ms, self._clock.now())
            if reply.correlation_id != command.message_id:
                raise self._error(
                    Mt4ErrorCode.SCHEMA_INVALID,
                    f"reply correlation_id {reply.correlation_id} does not match "
                    f"request {command.message_id}",
                )
        except Exception:
            self._metrics.observe_broker_request(operation, time.perf_counter() - began, "error")
            raise
        self._metrics.observe_broker_request(operation, time.perf_counter() - began, "ok")
        if reply.message_type is Mt4MessageType.HEARTBEAT:
            received_at = self._clock.now()
            self._monitor.on_heartbeat(received_at)
            self._metrics.set_mt4_heartbeat_age(0)
            self._metrics.set_mt4_heartbeat_timestamp(received_at.timestamp())
        return reply

    # ── Event / quote streams ─────────────────────────────────────────────
    def poll_event(self, timeout_ms: int = 0) -> WireMessage | None:
        """Poll one pushed event (non-blocking by default)."""
        if self._events is None:
            return None
        poller = zmq.Poller()
        poller.register(self._events, zmq.POLLIN)
        if not poller.poll(timeout_ms):
            return None
        raw = self._events.recv()
        event = parse_message(raw)
        if event.message_type is Mt4MessageType.HEARTBEAT:
            received_at = self._clock.now()
            self._monitor.on_heartbeat(received_at)
            self._metrics.set_mt4_heartbeat_age(0)
            self._metrics.set_mt4_heartbeat_timestamp(received_at.timestamp())
        return event

    def poll_quote(self, timeout_ms: int = 0) -> tuple[str, MarketQuote] | None:
        """Poll one market quote (non-blocking by default); returns (symbol, quote)."""
        if self._quotes is None:
            return None
        poller = zmq.Poller()
        poller.register(self._quotes, zmq.POLLIN)
        if not poller.poll(timeout_ms):
            return None
        topic, raw = self._quotes.recv_multipart()
        quote = MarketQuote.model_validate_json(raw.decode("utf-8"))
        # MQL4 bridges emit checksum:null (spec §9: verification optional).
        if quote.checksum is not None:
            quote.verify_checksum()
        self._metrics.set_market_data_age(
            "mt4", (self._clock.now() - quote.timestamp).total_seconds()
        )
        self._metrics.set_market_data_timestamp("mt4", quote.timestamp.timestamp())
        return topic.decode("utf-8"), quote

    def drain_events(self, timeout_ms: int = 50) -> list[WireMessage]:
        """Collect all currently queued events (used by lifecycle tests)."""
        events: list[WireMessage] = []
        while True:
            event = self.poll_event(timeout_ms=timeout_ms)
            if event is None:
                break
            events.append(event)
        return events

    # ── Internals ─────────────────────────────────────────────────────────
    def _next_sequence(self, strategy_id: str) -> int:
        self._sequences[strategy_id] = self._sequences.get(strategy_id, 0) + 1
        return self._sequences[strategy_id]

    def _assert_mutation_authorized(self, command: CommandMessage) -> None:
        """Fail closed: in live modes, cancel/modify need a deterministic
        mutation authorizer (emergency policy + matching live order) before
        anything reaches the socket (ADR-0025, INV-1)."""
        if self._operating_mode not in (OperatingMode.LIVE_GATED, OperatingMode.LIVE_AUTO):
            return
        if self._live_mutation_authorizer is None:
            raise self._internal(
                f"{self._operating_mode.value} order mutation lacks a mutation authorizer"
            )
        self._live_mutation_authorizer(command)

    def _error(self, code: Mt4ErrorCode, message: str) -> Mt4ProtocolError:
        return Mt4ProtocolError(ProtocolErrorDetail.create(code, message, now=self._clock.now()))

    def _internal(self, message: str) -> Mt4ProtocolError:
        return self._error(Mt4ErrorCode.INTERNAL_ERROR, message)
