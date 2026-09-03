"""Signal-parity fixtures and golden generation (mandate §46).

The two implementations of one strategy — this package and
``mt4/Experts/XauRpbEA.mq4`` — are only trustworthy if they agree. This module
defines canonical scenarios, runs the Python reference over them, and writes:

* ``<name>.csv``    — the input bars, readable by MQL4's ``FileOpen``;
* ``<name>.golden`` — the per-bar regime / state / signal the reference produced.

The MQL4 harness (``mt4/tests/XauRpbParityHarness.mq4``) consumes the same CSV and
writes ``<name>.actual``. ``tests/parity/`` then compares them field by field.

Legitimate divergence is limited to execution simulation (fill prices, slippage,
broker rejections). Regime, setup state, direction, entry bar and stop distance
must match exactly; anything else is a defect in one of the two implementations.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .backtest import aggregate_h1
from .config import StrategyConfig
from .indicators import atr as atr_series
from .regime import RegimeSeries
from .state_machine import SetupMachine
from .types import Bar

__all__ = ["PARITY_SCENARIOS", "ParityRow", "build_scenario", "generate_golden", "write_csv"]


@dataclass(frozen=True, slots=True)
class ParityRow:
    """One closed-M15-bar observation, as both sides must see it."""

    index: int
    bar_time: str
    regime: str
    state: str
    direction: str
    depth_atr: float
    breakout_reference: float
    atr_m15: float
    signal: int

    def as_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "bar_time": self.bar_time,
            "regime": self.regime,
            "state": self.state,
            "direction": self.direction,
            "depth_atr": round(self.depth_atr, 6),
            "breakout_reference": round(self.breakout_reference, 6),
            "atr_m15": round(self.atr_m15, 6),
            "signal": self.signal,
        }


def _bar(moment: datetime, o: float, h: float, low: float, c: float, spread: float) -> Bar:
    return Bar(moment, o, h, low, c, 100.0, spread)


def build_scenario(name: str, count: int = 4000) -> list[Bar]:
    """Deterministic scenarios that each exercise a different part of the spec.

    Seeded pseudo-random paths, not market data. Their only job is to drive both
    implementations through identical, reproducible state sequences.
    """
    # A STABLE seed: the built-in hash() is randomized per process (PYTHONHASHSEED),
    # which would make these "deterministic" fixtures differ between runs.
    digest = hashlib.sha256(name.encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    bars: list[Bar] = []
    moment = datetime(2024, 1, 1, 0, 0)
    price = 2000.0

    for i in range(count):
        if name == "trend_up":
            drift = 0.06
        elif name == "trend_down":
            drift = -0.06
        elif name == "range":
            drift = 0.5 * math.sin(i / 40.0) * 0.05
        elif name == "regime_flip":
            drift = 0.08 if i < count // 2 else -0.08
        elif name == "volatility_shock":
            drift = 0.05 if i % 900 else 0.0
        else:
            drift = 0.03 * math.sin(i / 500.0)

        scale = 1.0
        if name == "volatility_shock" and count // 2 <= i < count // 2 + 60:
            scale = 6.0   # a volatility burst, to exercise HIGH_VOLATILITY and ATR gates

        price += drift + rng.gauss(0, 0.6 * scale)
        open_ = price
        close = price + rng.gauss(0, 0.5 * scale)
        high = max(open_, close) + abs(rng.gauss(0, 0.35 * scale))
        low = min(open_, close) - abs(rng.gauss(0, 0.35 * scale))
        spread = 20.0 if scale == 1.0 else 45.0
        bars.append(_bar(moment, open_, high, low, close, spread))
        price = close
        moment += timedelta(minutes=15)
    return bars


PARITY_SCENARIOS: tuple[str, ...] = (
    "trend_up",
    "trend_down",
    "range",
    "regime_flip",
    "volatility_shock",
)


def write_csv(bars: list[Bar], path: Path) -> None:
    """Write bars in the exact column order the MQL4 harness expects."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["time", "open", "high", "low", "close", "volume", "spread"])
        for bar in bars:
            writer.writerow([
                bar.time.strftime("%Y.%m.%d %H:%M"),
                f"{bar.open:.5f}", f"{bar.high:.5f}",
                f"{bar.low:.5f}", f"{bar.close:.5f}",
                f"{bar.volume:.0f}", f"{bar.spread_points:.1f}",
            ])


def generate_golden(bars: list[Bar], config: StrategyConfig) -> list[ParityRow]:
    """Run the reference state machine and record what both sides must agree on.

    This deliberately drives the regime + setup machine only — not execution —
    because execution is where legitimate divergence lives.
    """
    h1 = aggregate_h1(bars)
    h1_times = [b.time for b in h1]
    regimes = RegimeSeries(h1, config.research)
    atr_m15 = atr_series(bars, config.research.atr_period_m15)
    machine = SetupMachine(config.research)

    rows: list[ParityRow] = []
    for i, bar in enumerate(bars):
        # The last H1 bar that had CLOSED before this M15 bar opened.
        h1_idx = -1
        lo, hi = 0, len(h1_times) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            if h1_times[mid] + timedelta(hours=1) <= bar.time:
                h1_idx = mid
                lo = mid + 1
            else:
                hi = mid - 1

        regime = regimes.at(h1_idx).regime
        atr_value = atr_m15[i] if i < len(atr_m15) else float("nan")
        signal = machine.on_closed_bar(bars, i, regime, atr_value)

        # A SIGNAL_READY is consumed immediately so the machine keeps advancing,
        # mirroring what the EA does after it evaluates score and guards.
        if signal:
            machine.on_signal_discarded(i, "PARITY_HARNESS_CONSUMED")

        direction = "" if machine.direction is None else machine.direction.code
        rows.append(
            ParityRow(
                index=i,
                bar_time=bar.time.strftime("%Y.%m.%d %H:%M"),
                regime=regime.value,
                state=machine.state.value,
                direction=direction,
                depth_atr=0.0 if math.isnan(machine.depth_atr) else machine.depth_atr,
                breakout_reference=machine.breakout_reference,
                atr_m15=0.0 if math.isnan(atr_value) else atr_value,
                signal=1 if signal else 0,
            )
        )
    return rows


def write_golden(rows: list[ParityRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_by": "research.strategies.xau_rpb.parity",
        "row_count": len(rows),
        "rows": [r.as_dict() for r in rows],
    }
    path.write_text(json.dumps(payload, indent=1), encoding="utf-8")
