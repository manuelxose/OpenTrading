"""Nautilus paper executor tests: fills, slippage, determinism, rejects."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from adapters.nautilus.paper import NautilusPaperExecutor, PaperVenueConfig
from core.domain.enums import ExecutionState, OperatingMode, OrderSide, OrderType
from core.schemas import OrderIntent
from core.schemas.base import Provenance

from factories import make_instrument, make_market_snapshot

NOW = datetime(2026, 8, 27, tzinfo=UTC)


def make_intent(
    side: OrderSide = OrderSide.BUY, quantity: Decimal = Decimal("100000")
) -> OrderIntent:
    return OrderIntent(
        order_intent_id=uuid4(),
        risk_decision_id=uuid4(),
        proposal_id=None,
        strategy_id="s",
        strategy_version="1",
        instrument_id="EURUSD",
        operating_mode=OperatingMode.PAPER,
        side=side,
        order_type=OrderType.MARKET,
        quantity=quantity,
        created_by="tests",
        produced_at=NOW,
        provenance=Provenance(producer="tests", produced_at=NOW),
    )


def make_snapshot() -> object:
    return make_market_snapshot(
        NOW,
        bid=Decimal("1.10000"),
        ask=Decimal("1.10001"),
        open=Decimal("1.10000"),
        high=Decimal("1.10050"),
        low=Decimal("1.09950"),
        close=Decimal("1.10000"),
        source="paper-executor-tests",
    )


def build_executor(slippage_ticks: int = 1) -> tuple[NautilusPaperExecutor, object]:
    config = PaperVenueConfig(seed=7, slippage_fixed_ticks=slippage_ticks)
    instrument = make_instrument(NOW)
    return NautilusPaperExecutor(config, instrument), instrument


class TestPaperExecutor:
    def test_market_buy_fills_with_reports(self) -> None:
        executor, _ = build_executor(slippage_ticks=0)
        reports = executor.submit(make_intent(OrderSide.BUY), make_snapshot())
        statuses = [report.status for report in reports]
        assert ExecutionState.SUBMITTED in statuses
        assert ExecutionState.ACKNOWLEDGED in statuses
        assert ExecutionState.FILLED in statuses
        fill = next(r for r in reports if r.status is ExecutionState.FILLED)
        assert fill.filled_quantity == Decimal("100000")
        assert fill.average_fill_price == Decimal("1.10001")  # the ask
        assert fill.commission > 0

    def test_slippage_ticks_shift_the_fill(self) -> None:
        executor, _ = build_executor(slippage_ticks=1)
        reports = executor.submit(make_intent(OrderSide.BUY), make_snapshot())
        fill = next(r for r in reports if r.status is ExecutionState.FILLED)
        assert fill.average_fill_price == Decimal("1.10002")  # ask + 1 tick

    def test_sell_fills_on_the_bid_side(self) -> None:
        executor, _ = build_executor(slippage_ticks=0)
        reports = executor.submit(make_intent(OrderSide.SELL), make_snapshot())
        fill = next(r for r in reports if r.status is ExecutionState.FILLED)
        assert fill.average_fill_price == Decimal("1.10000")  # the bid

    def test_deterministic_replays(self) -> None:
        executor, _ = build_executor(slippage_ticks=1)
        first = executor.submit(make_intent(OrderSide.BUY), make_snapshot())
        second = executor.submit(make_intent(OrderSide.BUY), make_snapshot())
        assert [r.status for r in first] == [r.status for r in second]
        assert [r.average_fill_price for r in first] == [r.average_fill_price for r in second]

    def test_undersized_order_is_rejected(self) -> None:
        executor, _ = build_executor()
        reports = executor.submit(
            make_intent(OrderSide.BUY, quantity=Decimal("1")), make_snapshot()
        )
        assert len(reports) == 1
        assert reports[0].status is ExecutionState.REJECTED
        assert reports[0].reject_reason is not None

    def test_reports_carry_order_intent_id(self) -> None:
        executor, _ = build_executor()
        intent = make_intent()
        reports = executor.submit(intent, make_snapshot())
        assert all(r.order_intent_id == intent.order_intent_id for r in reports)
