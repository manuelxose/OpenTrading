"""The minimal deterministic baseline: no LLMs, canonical OrderIntents only."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid5

from adapters.nautilus.strategy import BaselineSmaStrategy, StrategyContext
from core.domain.enums import OperatingMode, OrderSide, OrderType, TimeInForce
from core.schemas.base import Provenance

from conftest import make_config


def _ctx(close: Decimal, index: int, is_last: bool = False) -> StrategyContext:
    ts = datetime(2026, 1, 5, tzinfo=UTC) + timedelta(minutes=index)
    return StrategyContext(
        instrument_id="EURUSD",
        as_of=ts,
        open_=close,
        high=close,
        low=close,
        close=close,
        volume=Decimal("1"),
        position=None,
        last_bid=None,
        last_ask=None,
        is_last_bar=is_last,
        bars_remaining=1 if is_last else 99,
    )


def _config():
    cfg = make_config()
    return cfg.baseline


def test_baseline_emits_canonical_intents() -> None:
    strategy = BaselineSmaStrategy(_config())
    closes = [Decimal("1.08") + Decimal(i) * Decimal("0.00010") for i in range(25)]
    intents = []
    for i, close in enumerate(closes):
        intents.extend(strategy.on_bar(_ctx(close, i)))
    assert intents, "a rising series must trigger a LONG entry"
    for intent in intents:
        assert intent.operating_mode is OperatingMode.BACKTEST
        assert intent.order_type is OrderType.MARKET
        assert intent.time_in_force is TimeInForce.GTC
        assert intent.instrument_id == "EURUSD"
        assert intent.quantity == Decimal("100000")
        assert intent.created_by == "baseline-sma"


def test_baseline_is_deterministic() -> None:
    closes = [Decimal("1.08") + Decimal(i) * Decimal("0.00010") for i in range(40)]

    def run_once() -> list:
        strategy = BaselineSmaStrategy(_config())
        return [
            intent for i, close in enumerate(closes) for intent in strategy.on_bar(_ctx(close, i))
        ]

    first = run_once()
    second = run_once()
    assert [intent.canonical_dict() for intent in first] == [
        intent.canonical_dict() for intent in second
    ]


def test_baseline_uuid_scheme_is_content_derived() -> None:
    """Order intent ids come from uuid5(namespace, instrument:counter) — no randomness."""
    config = _config()
    namespace = UUID(config.intent_namespace)
    strategy = BaselineSmaStrategy(config)
    closes = [Decimal("1.08") + Decimal(i) * Decimal("0.00010") for i in range(30)]
    intents = []
    for i, close in enumerate(closes):
        intents.extend(strategy.on_bar(_ctx(close, i)))
    assert intents
    for n, intent in enumerate(intents):
        assert intent.order_intent_id == uuid5(namespace, f"EURUSD:{n}")
        assert intent.sequence == n


def test_baseline_alternates_entry_and_exit() -> None:
    strategy = BaselineSmaStrategy(_config())
    closes = [
        Decimal("1.0800"),
        Decimal("1.0810"),
        Decimal("1.0820"),
        Decimal("1.0830"),
        Decimal("1.0840"),
        Decimal("1.0850"),
        Decimal("1.0860"),
        Decimal("1.0870"),
        Decimal("1.0880"),
        Decimal("1.0890"),
        Decimal("1.0900"),
        Decimal("1.0910"),
        Decimal("1.0920"),
        Decimal("1.0930"),
        Decimal("1.0940"),
        Decimal("1.0950"),
        Decimal("1.0960"),
        Decimal("1.0970"),
        Decimal("1.0980"),
        Decimal("1.0990"),
        Decimal("1.1000"),
        Decimal("1.0990"),
        Decimal("1.0980"),
        Decimal("1.0970"),
        Decimal("1.0960"),
        Decimal("1.0950"),
        Decimal("1.0940"),
        Decimal("1.0930"),
        Decimal("1.0920"),
        Decimal("1.0910"),
    ]
    intents = []
    for i, close in enumerate(closes):
        intents.extend(strategy.on_bar(_ctx(close, i)))
    sides = [intent.side for intent in intents]
    assert sides[0] is OrderSide.BUY
    assert sides[1] is OrderSide.SELL  # the down leg crosses fast < slow


def test_exit_at_end_closes_final_position() -> None:
    strategy = BaselineSmaStrategy(_config())
    # Force a long position, then end the series on the last bar.
    closes = [Decimal("1.08") + Decimal(i) * Decimal("0.00010") for i in range(25)]
    intents = []
    for i, close in enumerate(closes):
        intents.extend(strategy.on_bar(_ctx(close, i)))
    assert intents and intents[0].side is OrderSide.BUY
    final = strategy.on_bar(_ctx(Decimal("1.10"), 25, is_last=True))
    assert final and final[0].side is OrderSide.SELL


def test_intent_carries_domain_provenance() -> None:
    strategy = BaselineSmaStrategy(_config())
    closes = [Decimal("1.08") + Decimal(i) * Decimal("0.00010") for i in range(25)]
    intents = []
    for i, close in enumerate(closes):
        intents.extend(strategy.on_bar(_ctx(close, i)))
    assert isinstance(intents[0].provenance, Provenance)
