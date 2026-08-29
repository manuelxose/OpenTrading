"""Execution-boundary hardening (ADR-0025): emergency closures and order
mutations are constrained to broker-protective actions.

These tests close the review findings F4/F5: an intent merely *tagged*
``CORE-EMERGENCY`` is not enough — it must structurally close a persisted open
position; and live-venue cancels/modifies require an active EMERGENCY_KILL
plus a matching live order.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from adapters.mt4.client import Mt4ExecutionClient
from core.domain.enums import (
    EmergencyLevel,
    OperatingMode,
    OrderSide,
    OrderType,
    PositionSide,
)
from core.schemas.execution import ExecutionPosition
from core.schemas.trading import OrderIntent
from engines.execution.emergency import (
    EmergencyController,
    EmergencyControlViolation,
    EmergencyPolicy,
    assert_emergency_closure_matches_positions,
)

from execution_helpers import Stack, make_intent

T = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


def make_position(
    instrument_id: str = "EURUSD",
    side: PositionSide = PositionSide.LONG,
    quantity: Decimal = Decimal("0.5"),
) -> ExecutionPosition:
    return ExecutionPosition(
        venue_position_id=f"pos-{instrument_id}",
        account_id="acct-1",
        instrument_id=instrument_id,
        side=side,
        quantity=quantity,
        average_entry_price=Decimal("1.1"),
        opened_at=T,
        updated_at=T,
    )


def make_closure(
    position: ExecutionPosition,
    *,
    side: OrderSide | None = None,
    order_type: OrderType = OrderType.MARKET,
) -> OrderIntent:
    offsetting = OrderSide.SELL if position.side is PositionSide.LONG else OrderSide.BUY
    return make_intent(
        strategy_id="CORE-EMERGENCY",
        instrument_id=position.instrument_id,
        side=side if side is not None else offsetting,
        quantity=position.quantity,
        order_type=order_type,
    )


class TestEmergencyClosureMustMatchOpenPosition:
    def test_accepts_offsetting_market_closure_of_open_position(self) -> None:
        long_eurgbp = make_position(instrument_id="EURGBP", side=PositionSide.LONG)
        assert_emergency_closure_matches_positions(
            [long_eurgbp], make_closure(long_eurgbp)
        )  # no raise

    def test_rejects_same_side_intent_tagged_emergency(self) -> None:
        long_eurgbp = make_position(instrument_id="EURGBP", side=PositionSide.LONG)
        with pytest.raises(EmergencyControlViolation):
            assert_emergency_closure_matches_positions(
                [long_eurgbp], make_closure(long_eurgbp, side=OrderSide.BUY)
            )

    def test_rejects_unknown_instrument(self) -> None:
        with pytest.raises(EmergencyControlViolation):
            assert_emergency_closure_matches_positions(
                [make_position(instrument_id="EURGBP")],
                make_closure(make_position(instrument_id="XAUUSD")),
            )

    def test_rejects_quantity_mismatch(self) -> None:
        position = make_position(quantity=Decimal("0.5"))
        intent = make_intent(
            strategy_id="CORE-EMERGENCY",
            instrument_id=position.instrument_id,
            side=OrderSide.SELL,
            quantity=Decimal("0.3"),
            order_type=OrderType.MARKET,
        )
        with pytest.raises(EmergencyControlViolation):
            assert_emergency_closure_matches_positions([position], intent)

    def test_rejects_non_market_orders(self) -> None:
        position = make_position()
        limit = make_intent(
            strategy_id="CORE-EMERGENCY",
            instrument_id=position.instrument_id,
            side=OrderSide.SELL,
            quantity=position.quantity,
            order_type=OrderType.LIMIT,
            price=Decimal("1.0"),
        )
        with pytest.raises(EmergencyControlViolation):
            assert_emergency_closure_matches_positions([position], limit)


class TestMutationAuthorization:
    def test_mutation_requires_active_emergency_kill(self) -> None:
        stack = Stack()
        controller = EmergencyController(
            stack.emergency_store, stack.clock, policy=EmergencyPolicy()
        )
        with pytest.raises(EmergencyControlViolation):
            controller.assert_mutation_authorized()

    def test_mutation_allowed_during_emergency_kill(self) -> None:
        stack = Stack()
        controller = EmergencyController(
            stack.emergency_store, stack.clock, policy=EmergencyPolicy()
        )
        controller.activate(EmergencyLevel.EMERGENCY_KILL, actor="ops", reason="test")
        controller.assert_mutation_authorized()  # no raise

    def test_live_gated_cancel_without_mutation_authorizer_fails_closed(self) -> None:
        def authorizer(intent: object) -> None:
            raise AssertionError("submit authorizer must not be invoked")

        client = Mt4ExecutionClient(
            operating_mode=OperatingMode.LIVE_GATED,
            live_authorizer=authorizer,  # type: ignore[arg-type]
        )
        with pytest.raises(Exception, match="mutation authorizer"):
            client.cancel_order(
                order_intent_id=UUID("00000000-0000-0000-0000-000000000001"),
                strategy_id="strategy-A",
                strategy_version="v1",
                symbol="EURUSD",
                side=OrderSide.BUY,
                quantity=Decimal("0.1"),
                order_type=OrderType.MARKET,
                reason="test",
            )
        client.close()

    def test_live_gated_modify_without_mutation_authorizer_fails_closed(self) -> None:
        def authorizer(intent: object) -> None:
            raise AssertionError("submit authorizer must not be invoked")

        client = Mt4ExecutionClient(
            operating_mode=OperatingMode.LIVE_GATED,
            live_authorizer=authorizer,  # type: ignore[arg-type]
        )
        with pytest.raises(Exception, match="mutation authorizer"):
            client.modify_order(
                order_intent_id=UUID("00000000-0000-0000-0000-000000000001"),
                strategy_id="strategy-A",
                strategy_version="v1",
                symbol="EURUSD",
                side=OrderSide.BUY,
                quantity=Decimal("0.1"),
                order_type=OrderType.MARKET,
                new_stop_loss=Decimal("1.0"),
            )
        client.close()

    def test_paper_mode_cancel_is_unaffected(self) -> None:
        client = Mt4ExecutionClient(operating_mode=OperatingMode.PAPER)
        assert client._operating_mode is OperatingMode.PAPER
        client.close()
