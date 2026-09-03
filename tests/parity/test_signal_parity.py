"""Signal parity between the Python reference and the MQL4 mirror (mandate §46).

Two implementations of one strategy are only trustworthy if they agree. This
module holds them to that.

Two layers run here:

1. **Golden self-consistency** (always runs). The reference must reproduce its own
   committed goldens bit for bit. This catches accidental behaviour changes in the
   Python side the moment they happen.

2. **MQL4 comparison** (runs only when `<scenario>.actual` is present). MetaTrader
   cannot be executed in CI, so the MQL4 side is produced by running
   `mt4/tests/XauRpbParityHarness.mq4` in a terminal and copying the output back.
   Until that has been done, these tests SKIP — and the skip is deliberately loud,
   because an unverified mirror is an open risk, not a passing result.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from research.strategies.xau_rpb.config import StrategyConfig
from research.strategies.xau_rpb.parity import (
    PARITY_SCENARIOS,
    build_scenario,
    generate_golden,
)

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "xau_rpb"

# Fields both implementations must agree on exactly. Execution-model outputs
# (fill price, slippage, broker rejection) are deliberately absent: that is where
# legitimate divergence lives.
EXACT_FIELDS = ("regime", "state", "direction", "signal")
NUMERIC_FIELDS = ("depth_atr", "breakout_reference", "atr_m15")

# Float tolerance. MQL4 and Python both use IEEE-754 doubles and the operation
# order is mirrored deliberately, so this only absorbs decimal formatting.
TOLERANCE = 1e-5


def _golden_path(scenario: str) -> Path:
    return FIXTURES / f"{scenario}.golden.json"


def _actual_path(scenario: str) -> Path:
    return FIXTURES / f"{scenario}.actual"


def _load_golden(scenario: str) -> list[dict]:
    path = _golden_path(scenario)
    if not path.is_file():
        pytest.fail(f"missing golden fixture {path}; regenerate with the parity module")
    return json.loads(path.read_text(encoding="utf-8"))["rows"]


def _load_actual(scenario: str) -> list[dict]:
    """Read the MQL4 harness output (CSV written by FileWrite)."""
    rows: list[dict] = []
    with _actual_path(scenario).open("r", encoding="ascii", newline="") as fh:
        for row in csv.DictReader(fh):
            rows.append(
                {
                    "index": int(row["index"]),
                    "regime": row["regime"].strip(),
                    "state": row["state"].strip(),
                    "direction": row["direction"].strip(),
                    "depth_atr": float(row["depth_atr"]),
                    "breakout_reference": float(row["breakout_reference"]),
                    "atr_m15": float(row["atr_m15"]),
                    "signal": int(row["signal"]),
                }
            )
    return rows


@pytest.mark.parametrize("scenario", PARITY_SCENARIOS)
def test_reference_reproduces_its_committed_golden(scenario: str) -> None:
    """The Python reference is deterministic and matches the committed fixture."""
    expected = _load_golden(scenario)
    bars = build_scenario(scenario, 4000)
    produced = [row.as_dict() for row in generate_golden(bars, StrategyConfig())]

    assert len(produced) == len(expected)
    for got, want in zip(produced, expected, strict=True):
        assert got == want, f"{scenario} diverged at bar {want['index']}"


@pytest.mark.parametrize("scenario", PARITY_SCENARIOS)
def test_golden_exercises_the_state_machine(scenario: str) -> None:
    """A fixture that never leaves SCANNING would make parity vacuously true."""
    rows = _load_golden(scenario)
    states = {row["state"] for row in rows}

    assert "ARMED" in states, f"{scenario} never armed a setup"
    assert "PULLBACK_ACTIVE" in states, f"{scenario} never entered a pullback"
    assert "BREAKOUT_WINDOW" in states, f"{scenario} never opened a breakout window"
    assert sum(row["signal"] for row in rows) > 0, f"{scenario} produced no signal"


@pytest.mark.parametrize("scenario", PARITY_SCENARIOS)
def test_mql4_matches_the_reference(scenario: str) -> None:
    """Field-by-field comparison against the MQL4 harness output."""
    actual_path = _actual_path(scenario)
    if not actual_path.is_file():
        pytest.skip(
            f"MQL4 parity NOT VERIFIED for '{scenario}': {actual_path.name} is absent. "
            "Run mt4/tests/XauRpbParityHarness.mq4 in a MetaTrader 4 terminal and copy "
            "the .actual file into data/fixtures/xau_rpb/. Until then the MQL4 mirror "
            "is unverified against the reference."
        )

    expected = _load_golden(scenario)
    actual = _load_actual(scenario)
    assert len(actual) == len(expected), (
        f"{scenario}: MQL4 produced {len(actual)} rows, reference produced {len(expected)}"
    )

    mismatches: list[str] = []
    for want, got in zip(expected, actual, strict=True):
        for field in EXACT_FIELDS:
            if want[field] != got[field]:
                mismatches.append(
                    f"bar {want['index']} {field}: reference={want[field]!r} mql4={got[field]!r}"
                )
        for field in NUMERIC_FIELDS:
            if abs(float(want[field]) - float(got[field])) > TOLERANCE:
                mismatches.append(
                    f"bar {want['index']} {field}: reference={want[field]} mql4={got[field]}"
                )
        if len(mismatches) >= 20:
            break

    assert not mismatches, (
        f"{scenario}: {len(mismatches)} parity divergence(s) — the implementations "
        "disagree, which is a defect in one of them:\n  " + "\n  ".join(mismatches[:20])
    )
