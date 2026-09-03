"""Parameter sets for XAU_RPB, split by the four categories of spec §14.

The split is not cosmetic. It is the mechanism that stops risk policy from being
quietly optimized into an alpha variable:

* ``StructuralParams``  — define the strategy. Changing one is a NEW SPEC VERSION.
* ``ResearchParams``    — the ONLY parameters a search may touch.
* ``RiskPolicyParams``  — mandate values. Never optimized, never searched.
* ``ExecutionParams``   — venue-dependent, tuned to the broker, never to the P&L.
* ``OperationalParams`` — no effect on signals at all.

Every run records ``StrategyConfig.config_hash()`` so a result can be tied back to
the exact parameters that produced it (spec §16, §51).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace
from typing import Any

__all__ = [
    "SPEC_VERSION",
    "ExecutionParams",
    "OperationalParams",
    "ResearchParams",
    "RiskPolicyParams",
    "StrategyConfig",
    "StructuralParams",
]

SPEC_VERSION = "XAU_RPB_V1.0.0"


@dataclass(frozen=True, slots=True)
class StructuralParams:
    """Spec §14 STRUCTURAL. Changing any of these requires a spec version bump."""

    use_closed_bars: bool = True
    regime_timeframe_minutes: int = 60
    setup_timeframe_minutes: int = 15
    breakout_on_close: bool = True
    max_concurrent_positions: int = 1


@dataclass(frozen=True, slots=True)
class ResearchParams:
    """Spec §14 RESEARCH. The only parameters an optimizer is permitted to vary."""

    # Regime engine (spec §4)
    ema_fast_period: int = 50
    ema_slow_period: int = 200
    adx_period: int = 14
    adx_trend_min: float = 20.0
    adx_range_max: float = 18.0
    spread_trend_min: float = 0.25
    slope_trend_min: float = 0.03
    slope_lookback: int = 3
    er_window: int = 20
    er_trend_min: float = 0.30
    atr_period_h1: int = 14
    atr_period_m15: int = 14
    atr_pct_window: int = 500
    atr_pct_high: float = 0.95
    atr_pct_floor: float = 0.10

    # Setup state machine (spec §5)
    impulse_lookback: int = 6
    min_pullback_bars: int = 1
    max_pullback_bars: int = 4
    min_pullback_depth_atr: float = 0.30
    max_pullback_depth_atr: float = 2.00
    breakout_window_bars: int = 3
    breakout_buffer_atr: float = 0.10
    max_setup_bars: int = 12

    # Scoring (spec §6)
    entry_score_threshold: int = 7
    score_slope_min: float = 0.03

    # Exits (spec §8)
    sl_atr_mult: float = 2.00
    tp_r_multiple: float = 0.0  # 0 = no fixed target (variant C)
    trail_atr_mult: float = 2.00
    trail_activate_r: float = 1.00
    be_trigger_r: float = 0.0  # 0 = break-even disabled
    max_bars_in_trade: int = 48

    def validate(self) -> None:
        """Reject internally contradictory parameter sets before any run starts."""
        if self.ema_fast_period >= self.ema_slow_period:
            raise ValueError("ema_fast_period must be < ema_slow_period")
        if self.adx_range_max > self.adx_trend_min:
            raise ValueError("adx_range_max must be <= adx_trend_min")
        if self.min_pullback_bars > self.max_pullback_bars:
            raise ValueError("min_pullback_bars must be <= max_pullback_bars")
        if self.min_pullback_depth_atr >= self.max_pullback_depth_atr:
            raise ValueError("min_pullback_depth_atr must be < max_pullback_depth_atr")
        if self.atr_pct_floor >= self.atr_pct_high:
            raise ValueError("atr_pct_floor must be < atr_pct_high")
        if not 0 <= self.entry_score_threshold <= 9:
            raise ValueError("entry_score_threshold must be within the 0..9 score range")
        if self.sl_atr_mult <= 0:
            raise ValueError("sl_atr_mult must be > 0")
        for name in ("ema_fast_period", "ema_slow_period", "adx_period", "er_window",
                     "atr_period_h1", "atr_period_m15", "atr_pct_window",
                     "impulse_lookback", "slope_lookback", "breakout_window_bars"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be >= 1")


@dataclass(frozen=True, slots=True)
class RiskPolicyParams:
    """Spec §14 RISK POLICY / §7.2. Mandate values — NEVER an optimization target."""

    risk_pct: float = 0.35
    max_aggregate_risk_pct: float = 0.75
    daily_loss_stop_pct: float = 1.5
    weekly_loss_stop_pct: float = 3.0
    soft_dd_pct: float = 5.0
    hard_dd_pct: float = 9.0
    soft_dd_risk_multiplier: float = 0.5

    # RESEARCH-ONLY. Production semantics are unchanged: the hard drawdown kill
    # LATCHES and needs an operator reset (spec §7.2). But in a backtest a latched
    # kill silently truncates the sample - the 2006-2012 run below stopped the
    # remaining 12 years of data from ever being measured. Setting this rebases the
    # peak and clears the kill at each year boundary so the FULL sample can be
    # characterized. It must never be enabled outside research, and any run using
    # it must say so.
    research_auto_reset_hard_kill: bool = False

    def validate(self) -> None:
        if not 0 < self.risk_pct <= 2.0:
            raise ValueError("risk_pct outside the sane 0-2% mandate band")
        if self.soft_dd_pct >= self.hard_dd_pct:
            raise ValueError("soft_dd_pct must be < hard_dd_pct")
        if self.daily_loss_stop_pct >= self.weekly_loss_stop_pct:
            raise ValueError("daily_loss_stop_pct must be < weekly_loss_stop_pct")


@dataclass(frozen=True, slots=True)
class ExecutionParams:
    """Spec §14 EXECUTION. Venue-dependent; tuned to the broker, never to the P&L."""

    # Venue calibration, NOT a P&L knob: typical XAUUSD spread/M15-ATR sits around
    # 0.05-0.12, so 0.12 admits normal microstructure and rejects genuine blowouts
    # (roughly 2x normal spread). Tightening this to 0.06 rejects almost every
    # valid setup; that was measured, not assumed.
    spread_atr_max: float = 0.12
    spread_abs_max_points: float = 60.0
    max_slippage_points: float = 20.0
    max_retries: int = 3
    retry_delay_ms: int = 250
    quote_max_age_sec: int = 5
    magic_number: int = 20260831
    symbol_aliases: tuple[str, ...] = (
        "XAUUSD", "GOLD", "XAUUSD.a", "XAUUSDm", "XAUUSD.m",
        "XAUUSD_i", "XAUUSDpro", "GOLD.a",
    )
    commission_per_lot: float = 0.0
    slippage_points_entry: float = 0.0
    slippage_points_exit: float = 0.0
    spread_multiplier: float = 1.0


@dataclass(frozen=True, slots=True)
class OperationalParams:
    """Spec §14 OPERATIONAL. No effect on signal generation whatsoever."""

    mode: str = "SHADOW"
    session_exit_enabled: bool = False
    news_required: bool = False
    news_block_before_min: int = 30
    news_block_after_min: int = 15
    broker_utc_offset_hours: float | None = None  # None = AUTO
    allow_asian_session: bool = False
    block_rollover: bool = True


@dataclass(frozen=True, slots=True)
class StrategyConfig:
    """The complete, hashable configuration of one strategy run."""

    spec_version: str = SPEC_VERSION
    structural: StructuralParams = field(default_factory=StructuralParams)
    research: ResearchParams = field(default_factory=ResearchParams)
    risk: RiskPolicyParams = field(default_factory=RiskPolicyParams)
    execution: ExecutionParams = field(default_factory=ExecutionParams)
    operational: OperationalParams = field(default_factory=OperationalParams)

    def validate(self) -> None:
        self.research.validate()
        self.risk.validate()

    def with_research(self, **overrides: Any) -> StrategyConfig:
        """Return a copy with RESEARCH parameters overridden.

        This is deliberately the only ergonomic override path: a sweep can vary
        research parameters and cannot accidentally vary risk policy.
        """
        return replace(self, research=replace(self.research, **overrides))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def config_hash(self) -> str:
        """Stable SHA-256 over the full configuration (spec §16, §51)."""
        blob = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    def warmup_bars_h1(self) -> int:
        """Closed H1 bars required before the regime engine may emit anything but INVALID."""
        r = self.research
        return max(
            r.ema_slow_period + 1,
            r.ema_fast_period + r.slope_lookback + 1,
            r.adx_period * 2 + 1,
            r.er_window + 1,
            r.atr_period_h1 + 1,
            r.atr_pct_window,
        )

    def warmup_bars_m15(self) -> int:
        """Closed M15 bars required before the setup machine may act."""
        r = self.research
        return max(r.atr_period_m15 + 1, r.impulse_lookback + 2)
