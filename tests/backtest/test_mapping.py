"""Unit tests for the domain ↔ NautilusTrader mappings (ADR-0007)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from adapters.nautilus.mapping import instrument_to_nautilus, order_intent_to_order
from core.domain.enums import OrderSide, OrderType, TimeInForce
from nautilus_trader.model.enums import TimeInForce as NTimeInForce
from nautilus_trader.model.identifiers import StrategyId, TraderId, Venue
from nautilus_trader.model.orders import LimitOrder, MarketOrder, StopLimitOrder, StopMarketOrder

from factories import FIXED_START, make_instrument, make_order_intent

TS = 1_700_000_000_000_000_000  # fixed 2023-11-14 timestamp in ns
TRADER_ID = TraderId("TESTER-001")
STRATEGY_ID = StrategyId("S-001-001")


@pytest.fixture
def nautilus_instrument():
    return instrument_to_nautilus(make_instrument(FIXED_START), Venue("SIM"))


def test_instrument_to_nautilus_maps_fx_rules(nautilus_instrument) -> None:
    assert nautilus_instrument.id.symbol.value == "EURUSD"
    assert nautilus_instrument.base_currency.code == "EUR"
    assert nautilus_instrument.quote_currency.code == "USD"
    assert nautilus_instrument.price_precision == 5
    assert nautilus_instrument.price_increment.as_decimal() == Decimal("0.00001")
    # size increment = lot_step * lot_size = 0.01 * 100000 = 1000 units
    assert nautilus_instrument.size_increment.as_decimal() == Decimal("1000")


def test_instrument_mapping_rejects_non_fx() -> None:
    instrument = make_instrument(FIXED_START, asset_class="EQUITY")
    with pytest.raises(NotImplementedError):
        instrument_to_nautilus(instrument, Venue("SIM"))


def test_market_intent_maps_to_market_order(nautilus_instrument) -> None:
    intent = make_order_intent(
        FIXED_START, order_type=OrderType.MARKET, side=OrderSide.BUY, quantity=Decimal("100000")
    )
    order = order_intent_to_order(intent, TRADER_ID, STRATEGY_ID, nautilus_instrument, TS)
    assert isinstance(order, MarketOrder)
    assert order.client_order_id.value == str(intent.order_intent_id)
    assert order.quantity.as_decimal() == Decimal("100000")
    assert order.side.name == "BUY"


@pytest.mark.parametrize(
    ("order_type", "expected_class", "price", "stop"),
    [
        (OrderType.LIMIT, LimitOrder, Decimal("1.08000"), None),
        (OrderType.STOP, StopMarketOrder, Decimal("1.08000"), None),
        (OrderType.STOP_LIMIT, StopLimitOrder, Decimal("1.08000"), Decimal("1.07900")),
    ],
)
def test_resting_intents_map_to_native_orders(
    nautilus_instrument, order_type, expected_class, price, stop
) -> None:
    intent = make_order_intent(
        FIXED_START,
        order_type=order_type,
        side=OrderSide.SELL,
        quantity=Decimal("100000"),
        price=price,
        stop_loss=stop,
        time_in_force=TimeInForce.DAY,
    )
    order = order_intent_to_order(intent, TRADER_ID, STRATEGY_ID, nautilus_instrument, TS)
    assert isinstance(order, expected_class)
    assert order.client_order_id.value == str(intent.order_intent_id)
    assert order.time_in_force is NTimeInForce.DAY


def test_stop_limit_requires_stop_loss(nautilus_instrument) -> None:
    intent = make_order_intent(
        FIXED_START,
        order_type=OrderType.STOP_LIMIT,
        quantity=Decimal("100000"),
        price=Decimal("1.08000"),
        stop_loss=None,
    )
    with pytest.raises(ValueError, match="stop_loss"):
        order_intent_to_order(intent, TRADER_ID, STRATEGY_ID, nautilus_instrument, TS)


def test_quantity_must_fit_size_precision(nautilus_instrument) -> None:
    intent = make_order_intent(FIXED_START, order_type=OrderType.MARKET, quantity=Decimal("0.10"))
    with pytest.raises(ValueError, match="size precision"):
        order_intent_to_order(intent, TRADER_ID, STRATEGY_ID, nautilus_instrument, TS)


def test_market_quantity_zero_not_allowed_by_domain() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        make_order_intent(FIXED_START, quantity=Decimal("0"))
