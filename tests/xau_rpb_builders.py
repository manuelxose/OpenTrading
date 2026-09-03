"""Bar builders for XAU_RPB strategy tests.

Bars here are hand-constructed to exercise a specific rule. They are FIXTURES,
never a claim about market behaviour, and no number produced from them is
evidence about the strategy's edge.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from research.strategies.xau_rpb import Bar

M15 = timedelta(minutes=15)
START = datetime(2024, 3, 4, 8, 0)  # a Monday, inside the London session


def bar(
    index: int,
    open_: float,
    high: float,
    low: float,
    close: float,
    *,
    start: datetime = START,
    step: timedelta = M15,
    spread_points: float = 20.0,
) -> Bar:
    """One bar at ``index`` steps after ``start``."""
    return Bar(
        time=start + index * step,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100.0,
        spread_points=spread_points,
    )


def trend_bar(index: int, base: float, direction: int, body: float = 2.0, **kw: object) -> Bar:
    """A bar closing ``body`` in ``direction`` from ``base``, with symmetric wicks."""
    open_ = base
    close = base + direction * body
    high = max(open_, close) + 0.5
    low = min(open_, close) - 0.5
    return bar(index, open_, high, low, close, **kw)  # type: ignore[arg-type]


def ramp(
    count: int,
    *,
    start_price: float = 2000.0,
    step_price: float = 1.0,
    start_index: int = 0,
    spread_points: float = 20.0,
) -> list[Bar]:
    """A clean monotonic ramp — used to drive the regime into a trend state."""
    bars: list[Bar] = []
    price = start_price
    for i in range(count):
        direction = 1 if step_price >= 0 else -1
        bars.append(
            trend_bar(
                start_index + i,
                price,
                direction,
                body=abs(step_price),
                spread_points=spread_points,
            )
        )
        price += step_price
    return bars
