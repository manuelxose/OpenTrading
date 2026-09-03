"""Static correspondence between the Python reference and the MQL4 mirror.

Full signal parity needs a MetaTrader terminal (see `test_signal_parity.py`), which
CI does not have. These checks do run in CI, and they catch the most likely way the
two implementations drift apart in practice: someone edits one side and forgets the
other.

They compare the *declared surface* — states, transition reasons, reject codes,
parameter defaults, spec version — by parsing both sources. That is not a proof of
behavioural equivalence, and it is not presented as one. It is a tripwire.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from research.strategies.xau_rpb.config import SPEC_VERSION, ResearchParams
from research.strategies.xau_rpb.types import RejectReason, SetupState

ROOT = Path(__file__).resolve().parents[2]
MQL_INCLUDE = ROOT / "mt4" / "Include" / "xau_rpb"
MQL_EA = ROOT / "mt4" / "Experts" / "XauRpbEA.mq4"
PY_STATE_MACHINE = ROOT / "research" / "strategies" / "xau_rpb" / "state_machine.py"


def _read(path: Path) -> str:
    assert path.is_file(), f"expected {path} to exist"
    return path.read_text(encoding="utf-8", errors="replace")


def test_the_mql4_sources_all_exist() -> None:
    expected = {
        "BrokerSpec.mqh", "Config.mqh", "Execution.mqh", "Indicators.mqh",
        "News.mqh", "Regime.mqh", "Risk.mqh", "Sessions.mqh",
        "SetupMachine.mqh", "Telemetry.mqh",
    }
    present = {p.name for p in MQL_INCLUDE.glob("*.mqh")}
    assert expected <= present, f"missing MQL4 modules: {sorted(expected - present)}"
    assert MQL_EA.is_file()


def test_spec_version_matches_across_implementations() -> None:
    config_mqh = _read(MQL_INCLUDE / "Config.mqh")
    match = re.search(r'#define\s+XAU_RPB_SPEC_VERSION\s+"([^"]+)"', config_mqh)
    assert match, "Config.mqh must define XAU_RPB_SPEC_VERSION"
    assert match.group(1) == SPEC_VERSION, (
        f"spec version drift: MQL4={match.group(1)} python={SPEC_VERSION}"
    )


def test_every_setup_state_exists_on_both_sides() -> None:
    config_mqh = _read(MQL_INCLUDE / "Config.mqh")
    for state in SetupState:
        assert f"STATE_{state.value}" in config_mqh, (
            f"MQL4 is missing the {state.value} state"
        )


def test_every_reject_reason_exists_on_both_sides() -> None:
    risk_mqh = _read(MQL_INCLUDE / "Risk.mqh")
    # Reasons the EA never raises because they are backtest-engine concepts.
    backtest_only = {RejectReason.POSITION_ALREADY_OPEN}
    for reason in RejectReason:
        if reason in backtest_only:
            continue
        assert f'"{reason.value}"' in risk_mqh, (
            f"MQL4 Risk.mqh does not define the {reason.value} reject code"
        )


def _python_transition_reasons() -> set[str]:
    """Reason strings the Python state machine can emit."""
    source = _read(PY_STATE_MACHINE)
    found = set(re.findall(r'_reset\(index,\s*"([A-Z_]+)"\)', source))
    found |= set(re.findall(r'SetupState\.\w+,\s*"([A-Z_]+)"\)', source))
    return found


def _mql4_transition_reasons() -> set[str]:
    source = _read(MQL_INCLUDE / "SetupMachine.mqh")
    found = set(re.findall(r'ResetSetup\("([A-Z_]+)"\)', source))
    found |= set(re.findall(r'Goto\(STATE_\w+,\s*"([A-Z_]+)"\)', source))
    return found


def test_state_machine_transition_reasons_correspond() -> None:
    """The reason vocabulary is the observable contract of the state machine."""
    python_reasons = _python_transition_reasons()
    mql4_reasons = _mql4_transition_reasons()

    core = {
        "PULLBACK_STARTED", "PULLBACK_COMPLETE", "BREAKOUT_CONFIRMED",
        "PULLBACK_TOO_LONG", "PULLBACK_TOO_DEEP", "PULLBACK_TOO_SHORT",
        "PULLBACK_TOO_SHALLOW", "STRUCTURE_LOST", "REGIME_INVALIDATED",
        "BREAKOUT_WINDOW_EXPIRED", "SETUP_LIFETIME_EXCEEDED", "ATR_INVALID",
    }
    missing_python = core - python_reasons
    missing_mql4 = core - mql4_reasons

    assert not missing_python, f"Python state machine lost reasons: {sorted(missing_python)}"
    assert not missing_mql4, f"MQL4 state machine lost reasons: {sorted(missing_mql4)}"


@pytest.mark.parametrize(
    "python_field,mql4_input",
    [
        ("ema_fast_period", "InpEmaFastPeriod"),
        ("ema_slow_period", "InpEmaSlowPeriod"),
        ("adx_period", "InpAdxPeriod"),
        ("adx_trend_min", "InpAdxTrendMin"),
        ("adx_range_max", "InpAdxRangeMax"),
        ("spread_trend_min", "InpSpreadTrendMin"),
        ("slope_trend_min", "InpSlopeTrendMin"),
        ("slope_lookback", "InpSlopeLookback"),
        ("er_window", "InpErWindow"),
        ("er_trend_min", "InpErTrendMin"),
        ("atr_period_h1", "InpAtrPeriodH1"),
        ("atr_period_m15", "InpAtrPeriodM15"),
        ("atr_pct_window", "InpAtrPctWindow"),
        ("atr_pct_high", "InpAtrPctHigh"),
        ("atr_pct_floor", "InpAtrPctFloor"),
        ("impulse_lookback", "InpImpulseLookback"),
        ("min_pullback_bars", "InpMinPullbackBars"),
        ("max_pullback_bars", "InpMaxPullbackBars"),
        ("min_pullback_depth_atr", "InpMinPullbackDepth"),
        ("max_pullback_depth_atr", "InpMaxPullbackDepth"),
        ("breakout_window_bars", "InpBreakoutWindowBars"),
        ("breakout_buffer_atr", "InpBreakoutBufferAtr"),
        ("max_setup_bars", "InpMaxSetupBars"),
        ("entry_score_threshold", "InpEntryScoreThresh"),
        ("score_slope_min", "InpScoreSlopeMin"),
        ("sl_atr_mult", "InpSlAtrMult"),
        ("tp_r_multiple", "InpTpRMultiple"),
        ("trail_atr_mult", "InpTrailAtrMult"),
        ("trail_activate_r", "InpTrailActivateR"),
        ("be_trigger_r", "InpBeTriggerR"),
        ("max_bars_in_trade", "InpMaxBarsInTrade"),
    ],
)
def test_research_parameter_defaults_match(python_field: str, mql4_input: str) -> None:
    """A silent default drift would make every parity run compare different strategies."""
    source = _read(MQL_EA)
    match = re.search(rf"input\s+\w+\s+{mql4_input}\s*=\s*([-\d.]+)\s*;", source)
    assert match, f"{mql4_input} not found among the EA inputs"

    mql4_value = float(match.group(1))
    python_value = float(getattr(ResearchParams(), python_field))
    assert mql4_value == pytest.approx(python_value), (
        f"default drift for {python_field}: python={python_value} mql4={mql4_value}"
    )


def test_the_parity_harness_uses_the_same_defaults() -> None:
    """The harness hardcodes its parameters; they must track ResearchParams."""
    harness = _read(ROOT / "mt4" / "tests" / "XauRpbParityHarness.mq4")
    defaults = ResearchParams()
    for field, literal in (
        ("ema_fast_period", "p.emaFastPeriod = 50"),
        ("ema_slow_period", "p.emaSlowPeriod = 200"),
        ("adx_trend_min", "p.adxTrendMin = 20.0"),
        ("breakout_buffer_atr", "p.breakoutBufferAtr = 0.10"),
        ("impulse_lookback", "p.impulseLookback = 6"),
        ("max_pullback_bars", "p.maxPullbackBars = 4"),
    ):
        assert literal in harness, f"parity harness must set {field} as {literal!r}"
    assert defaults.ema_fast_period == 50 and defaults.ema_slow_period == 200


def test_mql4_never_calls_ordersend_outside_the_execution_module() -> None:
    """Order submission must funnel through the guarded execution path (spec §9)."""
    for path in MQL_INCLUDE.glob("*.mqh"):
        if path.name == "Execution.mqh":
            continue
        assert "OrderSend(" not in _read(path), (
            f"{path.name} calls OrderSend directly, bypassing the execution guards"
        )
    ea = _read(MQL_EA)
    assert "OrderSend(" not in ea, "the EA must submit orders via SendMarketOrder only"


def test_the_ea_defaults_to_shadow_mode() -> None:
    """An unqualified strategy must not default to sending live orders."""
    source = _read(MQL_EA)
    match = re.search(r"input\s+RpbMode\s+InpMode\s*=\s*(\w+)\s*;", source)
    assert match, "InpMode input not found"
    assert match.group(1) == "MODE_SHADOW", (
        "the EA must default to SHADOW; it has not passed statistical qualification"
    )


def test_prohibited_strategy_families_are_absent_from_the_mql4_sources() -> None:
    """Spec §7.2 / §1: grid, martingale and averaging-down must not exist here."""
    banned = ("martingale", "averaging", "grid_recovery", "lot_multiplier", "recovery_lot")
    for path in [*MQL_INCLUDE.glob("*.mqh"), MQL_EA]:
        lowered = _read(path).lower()
        for term in banned:
            # The word may appear in a comment SAYING it is prohibited; only flag
            # it when it is not adjacent to a prohibition word.
            for hit in re.finditer(re.escape(term), lowered):
                window = lowered[max(0, hit.start() - 120): hit.end() + 120]
                assert any(
                    marker in window
                    for marker in ("prohibit", "never", "not ", "no ", "unrepresentable",
                                   "absent", "forbid")
                ), f"{path.name} references {term!r} outside a prohibition context"
