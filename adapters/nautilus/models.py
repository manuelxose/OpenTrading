"""Simulated execution models for the Nautilus venue: slippage + commission.

Both models are deterministic given the ``BacktestConfig`` seed (ADR-0007 forbids
nondeterministic simulations; the trading-cost-validation skill forbids cost-free
backtests).
"""

from __future__ import annotations

import random
from decimal import Decimal

from nautilus_trader.backtest.models import FeeModel, FillModel
from nautilus_trader.model.book import OrderBook
from nautilus_trader.model.data import BookOrder
from nautilus_trader.model.enums import BookType
from nautilus_trader.model.enums import OrderSide as NOrderSide
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.objects import Money, Price, Quantity
from nautilus_trader.model.orders import Order

__all__ = ["ConfigurableSlippageFillModel", "NotionalCommissionFeeModel"]

_UNLIMITED = 1_000_000  # Large enough to fill any order size used by the adapter


class ConfigurableSlippageFillModel(FillModel):  # type: ignore[misc]
    """Deterministic slippage by shifting the simulated order book away from best.

    Market orders fill ``fixed_ticks + rng(min..max)`` ticks worse than the best
    bid/ask. The random component is drawn from a seed-derived ``random.Random``,
    so identical configs always produce identical fills. With both components zero
    the model falls back to Nautilus default fill logic.
    """

    def __init__(
        self,
        fixed_ticks: int,
        random_min_ticks: int,
        random_max_ticks: int,
        seed: int,
        prob_fill_on_limit: float = 1.0,
        prob_fill_on_stop: float = 1.0,
    ) -> None:
        super().__init__(
            prob_fill_on_limit=prob_fill_on_limit,
            prob_fill_on_stop=prob_fill_on_stop,
            prob_slippage=0.0,
            random_seed=seed,
        )
        self._fixed_ticks = fixed_ticks
        self._random_min = random_min_ticks
        self._random_max = random_max_ticks
        self._rng = random.Random(seed + 97_153)
        #: client_order_id → (side, best_bid, best_ask) of the last fill simulation.
        self._theoretical: dict[str, tuple[NOrderSide, Decimal, Decimal]] = {}

    def theoretical(self, client_order_id: str) -> tuple[NOrderSide, Decimal, Decimal] | None:
        """The quote the most recent fill simulation used (for slippage accounting)."""
        return self._theoretical.get(client_order_id)

    def _ticks_for(self) -> int:
        extra = 0
        if self._random_max > 0:
            extra = self._rng.randint(self._random_min, self._random_max)
        return self._fixed_ticks + extra

    def get_orderbook_for_fill_simulation(
        self,
        instrument: Instrument,
        order: Order,
        best_bid: Price,
        best_ask: Price,
    ) -> OrderBook | None:
        """Return a book whose only levels sit ``ticks`` away from the touch."""
        self._theoretical[order.client_order_id.value] = (
            order.side,
            best_bid.as_decimal(),
            best_ask.as_decimal(),
        )
        ticks = self._ticks_for()
        if ticks <= 0:
            return None  # default fill logic: fill at best bid/ask
        tick = instrument.price_increment
        book = OrderBook(instrument_id=instrument.id, book_type=BookType.L2_MBP)
        precision = instrument.price_precision
        bid_px = best_bid.as_double()
        ask_px = best_ask.as_double()
        tick_px = tick.as_double()
        # The book's only levels sit ``ticks`` away from the touch: a market order
        # therefore fills at best +/- slippage. No zero-volume levels at the touch —
        # the matching engine would otherwise leave the order unfilled.
        book.add(
            BookOrder(
                side=NOrderSide.BUY,
                price=Price(bid_px - ticks * tick_px, precision),
                size=Quantity(_UNLIMITED, instrument.size_precision),
                order_id=1,
            ),
            0,
            0,
        )
        book.add(
            BookOrder(
                side=NOrderSide.SELL,
                price=Price(ask_px + ticks * tick_px, precision),
                size=Quantity(_UNLIMITED, instrument.size_precision),
                order_id=2,
            ),
            0,
            0,
        )
        return book


class NotionalCommissionFeeModel(FeeModel):  # type: ignore[misc]
    """Realistic commission: ``rate_bps`` of trade notional per fill, floored.

    For FX spot, notional is computed in the quote currency; commissions are
    charged in the quote currency of the traded instrument.
    """

    def __init__(self, rate_bps: Decimal, min_amount: Decimal) -> None:
        super().__init__()
        self._rate = rate_bps / Decimal("10000")
        self._min = min_amount

    def get_commission(
        self, order: Order, fill_qty: Quantity, fill_px: Price, instrument: Instrument
    ) -> Money:
        notional = fill_qty.as_decimal() * fill_px.as_decimal()
        amount = max(self._min, notional * self._rate)
        return Money(amount, instrument.quote_currency)
