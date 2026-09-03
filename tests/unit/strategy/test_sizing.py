"""Broker-aware position sizing (spec §7.1).

The two rules that carry the safety argument are asserted directly: sizing always
rounds DOWN, and it NEVER rounds up to reach the broker minimum. A sizing bug is
indistinguishable from a risk-limit bug in production, so the boundaries are
tested rather than assumed.
"""

from __future__ import annotations

import pytest
from research.strategies.xau_rpb import BrokerSpec, RejectReason, calculate_lots
from research.strategies.xau_rpb.sizing import floor_to_step


def test_lots_follow_the_textbook_risk_formula(standard_spec: BrokerSpec) -> None:
    # 100k equity, 0.5% risk = $500 budget. Stop is $10 wide; tick_size 0.01 and
    # tick_value $1 mean 1000 ticks at $1 = $1000 risk per lot => 0.5 lots.
    # Sanity: 0.5 lots x 100 oz = 50 oz, and a $10 move on 50 oz is exactly $500.
    result = calculate_lots(
        equity=100_000.0, risk_pct=0.5, entry_price=2000.0, stop_price=1990.0,
        spec=standard_spec,
    )
    assert result.is_tradeable
    assert result.risk_money == pytest.approx(500.0)
    assert result.risk_per_lot == pytest.approx(1000.0)
    assert result.lots == pytest.approx(0.5)
    assert result.actual_risk == pytest.approx(500.0)


def test_a_wider_stop_produces_a_smaller_position(standard_spec: BrokerSpec) -> None:
    narrow = calculate_lots(equity=100_000.0, risk_pct=0.35, entry_price=2000.0,
                            stop_price=1995.0, spec=standard_spec)
    wide = calculate_lots(equity=100_000.0, risk_pct=0.35, entry_price=2000.0,
                          stop_price=1980.0, spec=standard_spec)
    assert wide.lots < narrow.lots, "risk is held constant, so size must absorb the stop"


def test_realized_risk_never_exceeds_the_budget(standard_spec: BrokerSpec) -> None:
    for stop in (1999.37, 1993.11, 1987.5, 1971.23):
        r = calculate_lots(equity=50_000.0, risk_pct=0.35, entry_price=2000.0,
                           stop_price=stop, spec=standard_spec)
        if r.is_tradeable:
            assert r.actual_risk <= r.risk_money + 1e-9


def test_sizing_always_rounds_down_to_the_lot_step() -> None:
    spec = BrokerSpec("XAUUSD", point=0.01, digits=2, tick_value=1.0, tick_size=0.01,
                      lot_size=100.0, min_lot=0.1, max_lot=100.0, lot_step=0.1)
    r = calculate_lots(equity=1_000_000.0, risk_pct=0.35, entry_price=2000.0,
                       stop_price=1990.0, spec=spec)
    assert r.lots == pytest.approx(round(r.lots / 0.1) * 0.1, abs=1e-9)
    assert r.actual_risk <= r.risk_money + 1e-9


def test_below_minimum_lot_refuses_to_trade_rather_than_rounding_up(
    standard_spec: BrokerSpec,
) -> None:
    """The mandate rule: a broker minimum never justifies exceeding the risk budget."""
    r = calculate_lots(
        equity=100.0, risk_pct=0.35, entry_price=2000.0, stop_price=1900.0,
        spec=standard_spec,
    )
    assert not r.is_tradeable
    assert r.lots == 0.0
    assert r.reject_reason is RejectReason.RISK_SIZE_ZERO


def test_a_coarse_minimum_lot_broker_refuses_small_accounts(
    three_digit_spec: BrokerSpec,
) -> None:
    r = calculate_lots(equity=1_000.0, risk_pct=0.35, entry_price=2000.0,
                       stop_price=1990.0, spec=three_digit_spec)
    assert not r.is_tradeable, "0.1 min lot on a small account exceeds the risk mandate"


def test_size_is_capped_at_the_broker_maximum(standard_spec: BrokerSpec) -> None:
    r = calculate_lots(equity=100_000_000.0, risk_pct=0.35, entry_price=2000.0,
                       stop_price=1999.0, spec=standard_spec)
    assert r.lots <= standard_spec.max_lot


def test_a_zero_width_stop_is_refused(standard_spec: BrokerSpec) -> None:
    r = calculate_lots(equity=100_000.0, risk_pct=0.35, entry_price=2000.0,
                       stop_price=2000.0, spec=standard_spec)
    assert not r.is_tradeable
    assert r.reject_reason is RejectReason.RISK_SIZE_ZERO


@pytest.mark.parametrize(
    "field,value",
    [("point", 0.0), ("tick_value", 0.0), ("tick_size", 0.0),
     ("min_lot", 0.0), ("lot_step", 0.0), ("point", -0.01)],
)
def test_an_invalid_broker_spec_fails_closed(field: str, value: float) -> None:
    """Spec §15: a missing or nonsensical instrument spec means NO TRADE, not a default."""
    from dataclasses import replace

    spec = replace(
        BrokerSpec("XAUUSD", point=0.01, digits=2, tick_value=1.0, tick_size=0.01,
                   lot_size=100.0, min_lot=0.01, max_lot=50.0, lot_step=0.01),
        **{field: value},
    )
    r = calculate_lots(equity=100_000.0, risk_pct=0.35, entry_price=2000.0,
                       stop_price=1990.0, spec=spec)
    assert not r.is_tradeable
    assert r.reject_reason is RejectReason.BROKER_SPEC_INVALID


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_non_finite_inputs_fail_closed(standard_spec: BrokerSpec, bad: float) -> None:
    r = calculate_lots(equity=bad, risk_pct=0.35, entry_price=2000.0,
                       stop_price=1990.0, spec=standard_spec)
    assert not r.is_tradeable


def test_zero_or_negative_equity_is_refused(standard_spec: BrokerSpec) -> None:
    for equity in (0.0, -5000.0):
        r = calculate_lots(equity=equity, risk_pct=0.35, entry_price=2000.0,
                           stop_price=1990.0, spec=standard_spec)
        assert not r.is_tradeable


def test_sizing_is_portable_across_broker_digit_conventions(
    standard_spec: BrokerSpec, three_digit_spec: BrokerSpec
) -> None:
    """Same economic risk on a 2-digit and a 3-digit venue (spec §64)."""
    two = calculate_lots(equity=500_000.0, risk_pct=0.35, entry_price=2000.0,
                         stop_price=1990.0, spec=standard_spec)
    three = calculate_lots(equity=500_000.0, risk_pct=0.35, entry_price=2000.0,
                           stop_price=1990.0, spec=three_digit_spec)
    assert two.is_tradeable and three.is_tradeable
    assert two.actual_risk <= two.risk_money + 1e-9
    assert three.actual_risk <= three.risk_money + 1e-9


@pytest.mark.parametrize(
    "value,step,expected",
    [(0.3, 0.1, 0.3), (0.29999999, 0.1, 0.2), (1.0, 0.01, 1.0),
     (0.999999999, 0.01, 1.0), (0.0, 0.1, 0.0), (-1.0, 0.1, 0.0)],
)
def test_floor_to_step_handles_float_representation(
    value: float, step: float, expected: float
) -> None:
    assert floor_to_step(value, step) == pytest.approx(expected)


def test_floor_to_step_rejects_a_non_positive_step() -> None:
    with pytest.raises(ValueError):
        floor_to_step(1.0, 0.0)
