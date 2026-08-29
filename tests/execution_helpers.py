"""Shared builders for broker reconciliation and Safe Mode tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from adapters.mt4.errors import (
    Mt4ErrorCode,
    Mt4ProtocolError,
    ProtocolErrorDetail,
)
from adapters.mt4.protocol import (
    AccountState as WireAccountState,
)
from adapters.mt4.protocol import (
    FillEvent,
    OrderAck,
    OrderReject,
    PositionSnapshotEvent,
    ReconciliationResponse,
    VenuePosition,
    WireMessage,
)
from adapters.mt4.transport import ConnectionHealth
from core.audit.audit import AuditLogger, InMemoryAuditSink
from core.clock.clocks import Clock, VirtualClock
from core.domain.enums import OrderSide, OrderType, PositionSide
from core.schemas.base import Provenance
from core.schemas.execution import OrderRecord
from core.schemas.trading import OrderIntent, PositionSnapshot
from engines.execution.applier import OrderStateApplier
from engines.execution.emergency import EmergencyController, EmergencyPolicy
from engines.execution.emergency_persistence import InMemoryEmergencyStore
from engines.execution.events import InMemoryEventSink
from engines.execution.persistence import InMemoryExecutionStateStore
from engines.execution.reconciler import BrokerReconciler, BrokerView, VenueViewPosition
from engines.execution.safe_mode import InMemoryAlertSink, SafeModeController
from engines.execution.service import ExecutionService

T0 = datetime(2026, 8, 26, 10, 0, 0, tzinfo=UTC)


def new_clock() -> VirtualClock:
    return VirtualClock(T0)


def make_intent(t: datetime | None = None, **overrides: object) -> OrderIntent:
    base: dict[str, object] = {
        "order_intent_id": uuid4(),
        "risk_decision_id": uuid4(),
        "strategy_id": "strategy-A",
        "strategy_version": "1.0.0",
        "instrument_id": "EURUSD",
        "operating_mode": "PAPER",
        "side": OrderSide.BUY,
        "order_type": OrderType.MARKET,
        "quantity": Decimal("0.10"),
        "max_slippage": Decimal("0.0003"),
        "created_by": "tests",
        "produced_at": t or T0,
        "provenance": Provenance(producer="tests", produced_at=t or T0),
    }
    base.update(overrides)
    return OrderIntent.model_validate(base)


def make_position_snapshot(
    t: datetime,
    *,
    position_id: str = "pos-1",
    account_id: str = "acct-1",
    strategy_id: str | None = "strategy-A",
    instrument_id: str = "EURUSD",
    side: PositionSide = PositionSide.LONG,
    quantity: Decimal = Decimal("0.10"),
    average_entry_price: Decimal = Decimal("1.08000"),
    order_intent_id: UUID | None = None,
) -> PositionSnapshot:
    return PositionSnapshot(
        position_id=position_id,
        account_id=account_id,
        strategy_id=strategy_id,
        instrument_id=instrument_id,
        side=side,
        quantity=quantity,
        average_entry_price=average_entry_price,
        as_of=t,
        trace_id=order_intent_id,
        produced_at=t,
        provenance=Provenance(
            producer="mt4-emulator",
            produced_at=t,
            source_ids=(
                {"order_intent_id": str(order_intent_id)} if order_intent_id is not None else {}
            ),
        ),
    )


def make_venue_position(
    t: datetime,
    *,
    venue_position_id: str = "pos-1",
    magic: int = 12345,
    account_id: str = "acct-1",
    strategy_id: str | None = "strategy-A",
    instrument_id: str = "EURUSD",
    side: PositionSide = PositionSide.LONG,
    quantity: Decimal = Decimal("0.10"),
    average_entry_price: Decimal = Decimal("1.08000"),
    order_intent_id: UUID | None = None,
) -> VenuePosition:
    return VenuePosition(
        venue_position_id=venue_position_id,
        magic=magic,
        position=make_position_snapshot(
            t,
            position_id=venue_position_id,
            account_id=account_id,
            strategy_id=strategy_id,
            instrument_id=instrument_id,
            side=side,
            quantity=quantity,
            average_entry_price=average_entry_price,
            order_intent_id=order_intent_id,
        ),
    )


def make_account_state(t: datetime) -> WireAccountState:
    return WireAccountState(
        account_id="acct-1",
        currency="USD",
        balance=Decimal("10000"),
        equity=Decimal("10000"),
        margin=Decimal("0"),
        free_margin=Decimal("10000"),
        as_of=t,
    )


def make_reconciliation_response(
    t: datetime,
    *,
    positions: tuple[VenuePosition, ...] = (),
    open_order_intent_ids: tuple[UUID, ...] = (),
    last_sequences: dict[str, int] | None = None,
    broker_connected: bool = True,
    trading_enabled: bool = True,
) -> ReconciliationResponse:
    return ReconciliationResponse(
        message_id=uuid4(),
        timestamp=t,
        sequence=0,
        account=make_account_state(t),
        positions=positions,
        open_order_intent_ids=open_order_intent_ids,
        last_sequences=last_sequences if last_sequences is not None else {},
        broker_connected=broker_connected,
        trading_enabled=trading_enabled,
    )


def make_broker_view(
    *,
    positions: tuple[VenueViewPosition, ...] = (),
    open_order_intent_ids: tuple[UUID, ...] = (),
    last_sequences: dict[str, int] | None = None,
    broker_connected: bool = True,
    trading_enabled: bool = True,
    account: dict[str, object] | None = None,
) -> BrokerView:
    return BrokerView(
        account=account,
        positions=positions,
        open_order_intent_ids=open_order_intent_ids,
        broker_connected=broker_connected,
        trading_enabled=trading_enabled,
        last_sequences=last_sequences if last_sequences is not None else {},
    )


def make_venue_view_position(
    *,
    venue_position_id: str = "pos-1",
    magic: int = 12345,
    account_id: str = "acct-1",
    strategy_id: str | None = "strategy-A",
    instrument_id: str = "EURUSD",
    side: PositionSide = PositionSide.LONG,
    quantity: Decimal = Decimal("0.10"),
    average_entry_price: Decimal = Decimal("1.08000"),
    order_intent_id: UUID | None = None,
) -> VenueViewPosition:
    return VenueViewPosition(
        venue_position_id=venue_position_id,
        magic=magic,
        account_id=account_id,
        strategy_id=strategy_id,
        instrument_id=instrument_id,
        side=side,
        quantity=quantity,
        average_entry_price=average_entry_price,
        order_intent_id=order_intent_id,
    )


class Stack:
    """Wire the whole engine together over one store (tests inject doubles)."""

    def __init__(
        self,
        *,
        store: InMemoryExecutionStateStore | None = None,
        clock: Clock | None = None,
        emergency_store: InMemoryEmergencyStore | None = None,
        policy: EmergencyPolicy | None = None,
    ) -> None:
        self.store = store or InMemoryExecutionStateStore()
        self.clock = clock or new_clock()
        self.audit_sink = InMemoryAuditSink()
        self.audit = AuditLogger(self.audit_sink, self.clock)
        self.events = InMemoryEventSink()
        self.alerts = InMemoryAlertSink()
        self.applier = OrderStateApplier(self.store, self.clock)
        self.reconciler = BrokerReconciler(self.store, self.applier, self.clock)
        self.controller = SafeModeController(
            self.store,
            self.clock,
            audit=self.audit,
            events=self.events,
            alerts=self.alerts,
        )
        self.emergency_store = emergency_store or InMemoryEmergencyStore()
        self.emergency = EmergencyController(
            self.emergency_store,
            self.clock,
            policy=policy or EmergencyPolicy(),
            audit=self.audit,
            events=self.events,
            alerts=self.alerts,
        )

    def service(
        self,
        client: FakeReconcileClient,
        *,
        emergency: EmergencyController | None = None,
    ) -> ExecutionService:
        """Build an ExecutionService wired with this stack's pieces."""
        return ExecutionService(
            store=self.store,
            applier=self.applier,
            reconciler=self.reconciler,
            controller=self.controller,
            client=client,
            clock=self.clock,
            audit=self.audit,
            events=self.events,
            emergency=emergency if emergency is not None else self.emergency,
        )


def make_ack(order_intent_id: UUID, *, venue_order_id: str = "ord-1") -> OrderAck:
    return OrderAck(
        message_id=uuid4(),
        timestamp=T0,
        sequence=1,
        order_intent_id=order_intent_id,
        status="ACKNOWLEDGED",
        venue_order_id=venue_order_id,
    )


def make_fill_event(
    t: datetime,
    order_intent_id: UUID,
    *,
    quantity: Decimal = Decimal("0.10"),
    sequence: int = 1,
    venue_order_id: str = "ord-1",
    average_fill_price: Decimal = Decimal("1.08000"),
) -> FillEvent:
    return FillEvent(
        message_id=uuid4(),
        timestamp=t,
        sequence=sequence,
        order_intent_id=order_intent_id,
        venue_order_id=venue_order_id,
        filled_quantity=quantity,
        average_fill_price=average_fill_price,
        symbol="EURUSD",
        side=OrderSide.BUY,
    )


def make_position_snapshot_event(
    t: datetime,
    *,
    intent_id: UUID | None = None,
    account_id: str = "acct-1",
    venue_position_id: str = "pos-1",
) -> PositionSnapshotEvent:
    return PositionSnapshotEvent(
        message_id=uuid4(),
        timestamp=t,
        sequence=0,
        account_id=account_id,
        positions=(
            make_venue_position(
                t,
                venue_position_id=venue_position_id,
                order_intent_id=intent_id,
            ),
        ),
    )


def make_reject(order_intent_id: UUID, reason: str = "BROKER_ERROR") -> OrderReject:
    try:
        code = Mt4ErrorCode(reason)
    except ValueError:
        code = Mt4ErrorCode.BROKER_ERROR
    return OrderReject(
        message_id=uuid4(),
        timestamp=T0,
        sequence=1,
        order_intent_id=order_intent_id,
        error=ProtocolErrorDetail.create(
            code,
            reason,
            order_intent_id=order_intent_id,
            now=T0,
        ),
    )


def not_connected_error() -> Mt4ProtocolError:
    return Mt4ProtocolError(
        ProtocolErrorDetail.create(Mt4ErrorCode.NOT_CONNECTED, "broker unreachable", now=T0)
    )


class FakeReconcileClient:
    """Implements the service's ReconcileClient protocol without any sockets."""

    def __init__(self) -> None:
        self.responses: list[ReconciliationResponse] = []
        self.errors: list[BaseException] = []
        self.resynced: list[dict[str, int]] = []
        self.events: list[WireMessage] = []
        self.submitted: list[dict[str, object]] = []
        self.submit_reply: OrderAck | OrderReject | None = None
        self.submit_error: BaseException | None = None
        self.cancelled: list[dict[str, object]] = []
        self.cancel_reply: OrderAck | OrderReject | None = None

    def submit_order(self, **kwargs: object) -> OrderAck | OrderReject:
        self.submitted.append(kwargs)
        if self.submit_error is not None:
            raise self.submit_error
        if self.submit_reply is not None:
            return self.submit_reply
        return make_ack(UUID(str(kwargs["order_intent_id"])))

    def cancel_order(self, **kwargs: object) -> OrderAck | OrderReject:
        self.cancelled.append(kwargs)
        if self.cancel_reply is not None:
            return self.cancel_reply
        return make_ack(UUID(str(kwargs["order_intent_id"])))

    def reconcile(self, *, strategy_id: str = "CORE") -> ReconciliationResponse:
        if self.errors:
            raise self.errors.pop(0)
        if not self.responses:
            raise RuntimeError("FakeReconcileClient has no response queued")
        return self.responses.pop(0)

    def resync_sequences(self, mapping: dict[str, int]) -> None:
        self.resynced.append(dict(mapping))

    def connection_health(self) -> ConnectionHealth:
        return ConnectionHealth.CONNECTED

    def drain_events(self, timeout_ms: int = 50) -> list[WireMessage]:
        drained = self.events
        self.events = []
        return drained


def get_order(store: InMemoryExecutionStateStore, order_intent_id: UUID) -> OrderRecord:
    record = store.get_order(order_intent_id)
    assert record is not None
    return record
