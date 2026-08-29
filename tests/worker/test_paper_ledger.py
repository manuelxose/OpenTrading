"""PaperLedger tests: netting, closes, outcomes, account/portfolio views."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from apps.worker.ledger import PaperLedger
from core.clock.clocks import VirtualClock
from core.domain.enums import ExecutionState, OperatingMode, OrderSide, OrderType, PositionSide
from core.schemas import ExecutionReport
from core.schemas.base import Provenance
from core.schemas.execution import ExecutionPosition
from core.schemas.pipeline import PaperAccountRecord
from core.schemas.trading import OrderIntent

from factories import make_instrument

NOW = datetime(2026, 8, 27, tzinfo=UTC)


class _RecordingExecutionStore:
    """Minimal execution-store double recording only positions."""

    def __init__(self) -> None:
        self.positions: dict[str, ExecutionPosition] = {}

    def upsert_position(self, position: ExecutionPosition) -> ExecutionPosition:
        self.positions[position.venue_position_id] = position
        return position

    def list_positions(self, *, open_only: bool = True) -> tuple[ExecutionPosition, ...]:
        values = list(self.positions.values())
        if open_only:
            values = [p for p in values if p.closed_at is None]
        return tuple(values)


def make_intent(side: OrderSide, quantity: Decimal, instrument_id: str = "EURUSD") -> OrderIntent:
    return OrderIntent(
        order_intent_id=uuid4(),
        risk_decision_id=uuid4(),
        proposal_id=None,
        strategy_id="s",
        strategy_version="1",
        instrument_id=instrument_id,
        operating_mode=OperatingMode.PAPER,
        side=side,
        order_type=OrderType.MARKET,
        quantity=quantity,
        stop_loss=None,
        take_profit=None,
        created_by="tests",
        produced_at=NOW,
        provenance=Provenance(producer="tests", produced_at=NOW),
    )


def make_fill_report(
    intent: OrderIntent, price: Decimal, quantity: Decimal, commission: Decimal = Decimal("1.0")
) -> ExecutionReport:
    return ExecutionReport(
        execution_report_id=uuid4(),
        order_intent_id=intent.order_intent_id,
        venue="PAPER",
        status=ExecutionState.FILLED,
        filled_quantity=quantity,
        average_fill_price=price,
        commission=commission,
        report_time=NOW,
        sequence=1,
        produced_at=NOW,
        provenance=Provenance(producer="tests", produced_at=NOW),
    )


def build_ledger(clock: VirtualClock) -> tuple[PaperLedger, _RecordingExecutionStore]:
    store = _RecordingExecutionStore()
    ledger = PaperLedger(
        account_id="paper-account-001",
        currency="USD",
        lot_size=Decimal("100000"),
        instrument_by_id={"EURUSD": make_instrument(clock.now())},
        execution_store=store,
        clock=clock,
    )
    return ledger, store


def account_record() -> PaperAccountRecord:
    return PaperAccountRecord(
        account_id="paper-account-001",
        currency="USD",
        balance=Decimal("100000"),
        equity=Decimal("100000"),
        realized_pnl=Decimal("0"),
        daily_pnl=Decimal("0"),
        peak_equity=Decimal("100000"),
        consecutive_losses=0,
        last_loss_at=None,
        open_positions=0,
        version=1,
        updated_at=NOW,
    )


class TestOpenAndAdd:
    def test_open_position(self) -> None:
        clock = VirtualClock(NOW)
        ledger, store = build_ledger(clock)
        intent = make_intent(OrderSide.BUY, Decimal("100000"))
        application = ledger.apply_fill(
            make_fill_report(intent, Decimal("1.10000"), Decimal("100000")), intent, trace_id=None
        )
        assert application.outcome is None
        assert application.position is not None
        assert application.position.quantity == Decimal("100000")
        position = ledger.position("EURUSD")
        assert position is not None
        assert position.side is PositionSide.LONG
        assert position.quantity == Decimal("100000")
        # persisted with open state
        persisted = store.list_positions(open_only=True)
        assert len(persisted) == 1

    def test_add_to_position_averages_price(self) -> None:
        clock = VirtualClock(NOW)
        ledger, _ = build_ledger(clock)
        first = make_intent(OrderSide.BUY, Decimal("100000"))
        ledger.apply_fill(
            make_fill_report(first, Decimal("1.10000"), Decimal("100000")), first, trace_id=None
        )
        second = make_intent(OrderSide.BUY, Decimal("100000"))
        ledger.apply_fill(
            make_fill_report(second, Decimal("1.12000"), Decimal("100000")), second, trace_id=None
        )
        position = ledger.position("EURUSD")
        assert position is not None
        assert position.quantity == Decimal("200000")
        assert position.average_entry_price == Decimal("1.11000")


class TestClose:
    def test_close_realizes_profit_long(self) -> None:
        clock = VirtualClock(NOW)
        ledger, store = build_ledger(clock)
        entry = make_intent(OrderSide.BUY, Decimal("100000"))
        ledger.apply_fill(
            make_fill_report(entry, Decimal("1.10000"), Decimal("100000")), entry, trace_id=None
        )
        close = make_intent(OrderSide.SELL, Decimal("100000"))
        application = ledger.apply_fill(
            make_fill_report(close, Decimal("1.11000"), Decimal("100000")),
            close,
            trace_id=UUID(int=0),
        )
        assert application.outcome is not None
        # 1000 USD profit gross minus 1 USD commission reported on the fill
        assert application.outcome.realized_pnl == Decimal("1000")
        assert application.outcome.costs >= Decimal("1")
        assert application.outcome.entry_price == Decimal("1.10000")
        assert application.outcome.exit_price == Decimal("1.11000")
        assert application.realized_pnl == Decimal("1000")
        assert ledger.position("EURUSD") is None
        persisted = store.list_positions(open_only=True)
        assert persisted == ()
        closed = next(p for p in store.positions.values() if p.instrument_id == "EURUSD")
        assert closed.closed_at is not None

    def test_close_realizes_loss_short(self) -> None:
        clock = VirtualClock(NOW)
        ledger, _ = build_ledger(clock)
        entry = make_intent(OrderSide.SELL, Decimal("100000"))
        ledger.apply_fill(
            make_fill_report(entry, Decimal("1.11000"), Decimal("100000")), entry, trace_id=None
        )
        close = make_intent(OrderSide.BUY, Decimal("100000"))
        application = ledger.apply_fill(
            make_fill_report(close, Decimal("1.12000"), Decimal("100000")), close, trace_id=None
        )
        assert application.outcome is not None
        assert application.outcome.realized_pnl == Decimal("-1000")

    def test_partial_close_keeps_residual(self) -> None:
        clock = VirtualClock(NOW)
        ledger, _ = build_ledger(clock)
        entry = make_intent(OrderSide.BUY, Decimal("200000"))
        ledger.apply_fill(
            make_fill_report(entry, Decimal("1.10000"), Decimal("200000")), entry, trace_id=None
        )
        close = make_intent(OrderSide.SELL, Decimal("50000"))
        application = ledger.apply_fill(
            make_fill_report(close, Decimal("1.11000"), Decimal("50000")), close, trace_id=None
        )
        assert application.outcome is None  # still open
        assert application.realized_pnl == Decimal("500")
        position = ledger.position("EURUSD")
        assert position is not None
        assert position.quantity == Decimal("150000")


class TestViews:
    def test_account_state_view(self) -> None:
        clock = VirtualClock(NOW)
        ledger, _ = build_ledger(clock)
        account = account_record()
        state = ledger.account_state(account, now=NOW)
        assert state.account_id == account.account_id
        assert state.balance == Decimal("100000")
        assert state.equity == Decimal("100000")
        assert state.broker_connected is True

    def test_portfolio_state_view_with_marks(self) -> None:
        clock = VirtualClock(NOW)
        ledger, _ = build_ledger(clock)
        entry = make_intent(OrderSide.BUY, Decimal("100000"))
        ledger.apply_fill(
            make_fill_report(entry, Decimal("1.10000"), Decimal("100000")), entry, trace_id=None
        )
        portfolio = ledger.portfolio_state(
            account_record(),
            marks={"EURUSD": Decimal("1.11000")},
            pending_orders=0,
            now=NOW,
        )
        assert len(portfolio.positions) == 1
        assert portfolio.positions[0].mark_price == Decimal("1.11000")
        assert portfolio.positions[0].unrealized_pnl == Decimal("1000")
        assert portfolio.exposure.by_instrument["EURUSD"] == Decimal("111000")

    def test_load_rebuilds_positions_after_restart(self) -> None:
        clock = VirtualClock(NOW)
        ledger, store = build_ledger(clock)
        entry = make_intent(OrderSide.BUY, Decimal("100000"))
        ledger.apply_fill(
            make_fill_report(entry, Decimal("1.10000"), Decimal("100000")), entry, trace_id=None
        )
        # a "restarted" ledger starts empty and rebuilds from the store
        rebuilt = PaperLedger(
            account_id="paper-account-001",
            currency="USD",
            lot_size=Decimal("100000"),
            instrument_by_id={"EURUSD": make_instrument(clock.now())},
            execution_store=store,
            clock=clock,
        )
        rebuilt.load(store.list_positions(open_only=True))
        position = rebuilt.position("EURUSD")
        assert position is not None
        assert position.quantity == Decimal("100000")
        assert position.average_entry_price == Decimal("1.10000")
