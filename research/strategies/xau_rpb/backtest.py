"""Deterministic event-driven backtest for XAU_RPB (spec §2, §8, §9; mandate §41).

Execution model — stated explicitly, because an unstated one is how backtests lie:

* **Signal on close, fill on next open.** A breakout is confirmed at the close of
  M15 bar ``i``; the earliest price the strategy could actually transact at is the
  open of bar ``i+1``. There is no same-bar fill anywhere in this engine.
* **Bar OHLC are treated as bid/mid quotes.** A round trip pays the full spread
  once, charged adversely at entry, plus configured slippage at entry and exit,
  plus commission per lot.
* **Stop precedence within a bar.** When a bar's range contains both the stop and
  the target, the STOP is assumed to have been hit first. Bar data cannot resolve
  the intrabar path, so the pessimistic branch is taken.
* **Trailing and break-even move only on closed bars**, and a stop only ever moves
  in the favorable direction (spec §8).

These assumptions make the result conservative rather than flattering, and they are
recorded in every run's config snapshot so a number can be traced to the model that
produced it.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .config import StrategyConfig
from .indicators import atr as atr_series
from .indicators import is_finite
from .news import NewsCalendar
from .regime import RegimeSeries
from .risk_limits import RiskGovernor
from .scoring import compute_score
from .sessions import SessionResolver
from .sizing import calculate_lots
from .state_machine import SetupMachine
from .types import (
    Bar,
    BrokerSpec,
    Direction,
    ExitReason,
    Regime,
    RejectReason,
    SetupState,
    Trade,
)

__all__ = ["BacktestResult", "run_backtest"]


@dataclass(slots=True)
class _OpenPosition:
    trade: Trade
    target_price: float | None
    extreme: float
    bars_held: int = 0
    be_applied: bool = False
    trail_active: bool = False
    last_swap_day: int = -1


@dataclass(slots=True)
class BacktestResult:
    """Everything a run produced, including what it REFUSED to do and why."""

    trades: list[Trade] = field(default_factory=list)
    equity_curve: list[tuple[datetime, float]] = field(default_factory=list)
    rejections: dict[str, int] = field(default_factory=dict)
    regime_bar_counts: dict[str, int] = field(default_factory=dict)
    telemetry: list[dict[str, object]] = field(default_factory=list)
    config_hash: str = ""
    spec_version: str = ""
    initial_equity: float = 0.0
    final_equity: float = 0.0
    bars_processed: int = 0
    warmup_bars: int = 0

    def record_rejection(self, reason: str) -> None:
        self.rejections[reason] = self.rejections.get(reason, 0) + 1


def _h1_index_for(m15_time: datetime, h1_times: Sequence[datetime]) -> int:
    """Index of the last H1 bar that had CLOSED before ``m15_time``.

    An H1 bar opening at ``t`` closes at ``t + 1h``; it is only usable once the
    M15 bar under evaluation opens at or after that close. This is the guard that
    keeps the regime free of look-ahead.
    """
    lo, hi = 0, len(h1_times) - 1
    result = -1
    while lo <= hi:
        mid = (lo + hi) // 2
        if h1_times[mid] + timedelta(hours=1) <= m15_time:
            result = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return result


def aggregate_h1(m15_bars: Sequence[Bar]) -> list[Bar]:
    """Build H1 bars from M15 bars, keeping only fully-formed hours."""
    buckets: dict[datetime, list[Bar]] = {}
    for bar in m15_bars:
        key = bar.time.replace(minute=0, second=0, microsecond=0)
        buckets.setdefault(key, []).append(bar)

    out: list[Bar] = []
    for key in sorted(buckets):
        group = buckets[key]
        if len(group) < 4:
            continue  # partial hour: never used for a regime decision
        out.append(
            Bar(
                time=key,
                open=group[0].open,
                high=max(b.high for b in group),
                low=min(b.low for b in group),
                close=group[-1].close,
                volume=math.fsum(b.volume for b in group),
                spread_points=group[-1].spread_points,
            )
        )
    return out


def run_backtest(
    m15_bars: Sequence[Bar],
    config: StrategyConfig,
    spec: BrokerSpec,
    *,
    initial_equity: float = 100_000.0,
    h1_bars: Sequence[Bar] | None = None,
    news: NewsCalendar | None = None,
    broker_utc_offset_hours: float | Callable[[datetime], float] = 0.0,
    collect_telemetry: bool = False,
) -> BacktestResult:
    """Run the strategy over ``m15_bars`` and return trades, equity and rejections."""
    config.validate()
    p = config.research
    ex = config.execution
    op = config.operational

    h1 = list(h1_bars) if h1_bars is not None else aggregate_h1(m15_bars)
    h1_times = [b.time for b in h1]
    regimes = RegimeSeries(h1, p)
    atr_m15 = atr_series(m15_bars, p.atr_period_m15)

    sessions = SessionResolver(
        broker_utc_offset_hours,
        allow_asian=op.allow_asian_session,
        block_rollover=op.block_rollover,
    )
    calendar = news if news is not None else NewsCalendar.empty(required=op.news_required)
    governor = RiskGovernor(config.risk)
    machine = SetupMachine(p)

    result = BacktestResult(
        config_hash=config.config_hash(),
        spec_version=config.spec_version,
        initial_equity=initial_equity,
        warmup_bars=config.warmup_bars_m15(),
    )

    equity = initial_equity
    position: _OpenPosition | None = None
    pending: tuple[Direction, float, float, int, Regime] | None = None
    last_signal_bar = -1

    for i, bar in enumerate(m15_bars):
        if not bar.is_valid():
            result.record_rejection("BAR_INVALID")
            continue

        governor.observe(bar.time, equity)

        h1_idx = _h1_index_for(bar.time, h1_times)
        features = regimes.at(h1_idx)
        regime = features.regime
        result.regime_bar_counts[regime.value] = result.regime_bar_counts.get(regime.value, 0) + 1

        current_atr = atr_m15[i] if i < len(atr_m15) else float("nan")

        # 1) Fill a pending entry at THIS bar's open (signalled on the previous close).
        if pending is not None and position is None:
            direction, stop_price, signal_atr, score, entry_regime = pending
            pending = None
            position, equity = _open_position(
                bar=bar,
                direction=direction,
                stop_price=stop_price,
                signal_atr=signal_atr,
                score=score,
                regime=entry_regime,
                equity=equity,
                spec=spec,
                config=config,
                governor=governor,
                result=result,
                machine=machine,
                bar_index=i,
            )

        # 2) Manage an open position before considering anything new.
        if position is not None:
            closed, equity = _manage_position(
                position=position,
                bar=bar,
                regime=regime,
                equity=equity,
                spec=spec,
                config=config,
                sessions=sessions,
                result=result,
            )
            if closed:
                machine.on_position_closed(i, str(position.trade.exit_reason))
                position = None

        result.equity_curve.append((bar.time, equity))
        result.bars_processed += 1

        if i < config.warmup_bars_m15():
            continue

        # 3) Advance the setup machine on this CLOSED bar.
        if position is not None:
            continue
        ready = machine.on_closed_bar(m15_bars, i, regime, current_atr)
        if not ready or machine.direction is None:
            continue

        # 4) SIGNAL_READY: score, then guards, then sizing (spec §5.5).
        if i == last_signal_bar:
            machine.on_signal_discarded(i, RejectReason.DUPLICATE_SIGNAL.value)
            result.record_rejection(RejectReason.DUPLICATE_SIGNAL.value)
            continue

        direction = machine.direction
        session_ok = sessions.is_permitted(bar.time)
        effective_spread = bar.spread_points * ex.spread_multiplier

        breakdown = compute_score(
            regime=regime,
            direction=direction,
            normalized_slope=features.normalized_slope,
            atr_pct=features.atr_pct,
            depth_atr=machine.depth_atr,
            breakout_confirmed=True,
            session_permitted=session_ok,
            spread_points=effective_spread,
            atr_m15=current_atr,
            params=p,
            spread_atr_max=ex.spread_atr_max,
            spread_abs_max_points=ex.spread_abs_max_points,
            point=spec.point,
        )

        reject = _entry_guards(
            breakdown_total=breakdown.total,
            threshold=p.entry_score_threshold,
            session_ok=session_ok,
            spread_ok=breakdown.spread_ok == 1,
            blackout=calendar.is_blackout(sessions.to_utc(bar.time)),
            governor=governor,
            atr_value=current_atr,
        )
        if reject is not None:
            machine.on_signal_discarded(i, reject.value)
            result.record_rejection(reject.value)
            continue

        stop_price = (
            bar.close - p.sl_atr_mult * current_atr
            if direction is Direction.LONG
            else bar.close + p.sl_atr_mult * current_atr
        )
        sizing = calculate_lots(
            equity=equity,
            risk_pct=governor.effective_risk_pct(),
            entry_price=bar.close,
            stop_price=stop_price,
            spec=spec,
        )
        if not sizing.is_tradeable:
            reason = (sizing.reject_reason or RejectReason.RISK_SIZE_ZERO).value
            machine.on_signal_discarded(i, reason)
            result.record_rejection(reason)
            continue

        # Stop distance must survive the broker's minimum stop distance (spec §9).
        if spec.stop_level_points > 0:
            min_distance = spec.stop_level_points * spec.point
            if abs(bar.close - stop_price) < min_distance:
                machine.on_signal_discarded(i, RejectReason.STOP_LEVEL_VIOLATION.value)
                result.record_rejection(RejectReason.STOP_LEVEL_VIOLATION.value)
                continue

        machine.on_order_submitted(i)
        pending = (direction, stop_price, current_atr, breakdown.total, regime)
        last_signal_bar = i

        if collect_telemetry:
            result.telemetry.append(
                {
                    "bar_time": bar.time.isoformat(),
                    "spec_version": config.spec_version,
                    "config_hash": result.config_hash,
                    "regime": regime.value,
                    "adx": features.adx,
                    "er": features.er,
                    "atr_h1": features.atr_h1,
                    "atr_m15": current_atr,
                    "normalized_spread": features.normalized_spread,
                    "normalized_slope": features.normalized_slope,
                    "atr_pct": features.atr_pct,
                    "direction": direction.code,
                    "depth_atr": machine.depth_atr,
                    "breakout_reference": machine.breakout_reference,
                    "score": breakdown.total,
                    **{f"score_{k}": v for k, v in breakdown.as_dict().items()},
                    "stop_price": stop_price,
                    "lots": sizing.lots,
                    "risk_money": sizing.risk_money,
                    "session": sessions.flags(bar.time).label,
                    "spread_points": effective_spread,
                }
            )

    # Mark-to-market any position still open at the end of the data.
    if position is not None and m15_bars:
        equity = _close_position(
            position, m15_bars[-1].time, m15_bars[-1].close, ExitReason.MANUAL, equity, spec,
            config, result,
        )

    result.final_equity = equity
    return result


def _entry_guards(
    *,
    breakdown_total: int,
    threshold: int,
    session_ok: bool,
    spread_ok: bool,
    blackout: bool,
    governor: RiskGovernor,
    atr_value: float,
) -> RejectReason | None:
    """Execution guards of spec §9. Order is severity-first for clean telemetry."""
    if not is_finite(atr_value) or atr_value <= 0:
        return RejectReason.ATR_INVALID
    block = governor.entry_block_reason()
    if block is not None:
        return block
    if blackout:
        return RejectReason.NEWS_BLACKOUT
    if not session_ok:
        return RejectReason.SESSION_BLOCKED
    if not spread_ok:
        return RejectReason.SPREAD_TOO_WIDE
    if breakdown_total < threshold:
        return RejectReason.SCORE_BELOW_THRESHOLD
    return None


def _open_position(
    *,
    bar: Bar,
    direction: Direction,
    stop_price: float,
    signal_atr: float,
    score: int,
    regime: Regime,
    equity: float,
    spec: BrokerSpec,
    config: StrategyConfig,
    governor: RiskGovernor,
    result: BacktestResult,
    machine: SetupMachine,
    bar_index: int,
) -> tuple[_OpenPosition | None, float]:
    """Fill at this bar's open, charging spread and entry slippage adversely."""
    ex = config.execution
    spread_price = bar.spread_points * ex.spread_multiplier * spec.point
    slip = ex.slippage_points_entry * spec.point
    sign = 1.0 if direction is Direction.LONG else -1.0
    entry_price = bar.open + sign * (spread_price + slip)

    sizing = calculate_lots(
        equity=equity,
        risk_pct=governor.effective_risk_pct(),
        entry_price=entry_price,
        stop_price=stop_price,
        spec=spec,
    )
    if not sizing.is_tradeable:
        reason = (sizing.reject_reason or RejectReason.RISK_SIZE_ZERO).value
        machine.on_rejected(bar_index, reason)
        result.record_rejection(reason)
        return None, equity

    commission = ex.commission_per_lot * sizing.lots
    equity -= commission

    trade = Trade(
        entry_time=bar.time,
        direction=direction,
        entry_price=entry_price,
        stop_price=stop_price,
        initial_stop_price=stop_price,
        lots=sizing.lots,
        atr_at_signal=signal_atr,
        score=score,
        regime_at_entry=regime,
        risk_amount=sizing.actual_risk,
        entry_slippage=abs(sign * (spread_price + slip)),
        costs=commission,
    )
    target = None
    if config.research.tp_r_multiple > 0:
        r_distance = abs(entry_price - stop_price)
        target = entry_price + sign * config.research.tp_r_multiple * r_distance

    machine.on_filled(bar_index)
    return _OpenPosition(trade=trade, target_price=target, extreme=entry_price), equity


def _value_per_price_unit(lots: float, spec: BrokerSpec) -> float:
    """Account-currency value of a one-price-unit move for ``lots`` (broker-derived)."""
    tick_size_price = spec.tick_size  # a PRICE increment (see sizing.calculate_lots)
    if tick_size_price <= 0:
        return 0.0
    return lots * spec.tick_value / tick_size_price


def _manage_position(
    *,
    position: _OpenPosition,
    bar: Bar,
    regime: Regime,
    equity: float,
    spec: BrokerSpec,
    config: StrategyConfig,
    sessions: SessionResolver,
    result: BacktestResult,
) -> tuple[bool, float]:
    """Advance one open position by one bar. Returns ``(closed, equity)``."""
    p = config.research
    trade = position.trade
    long_side = trade.direction is Direction.LONG
    position.bars_held += 1

    # MAE / MFE on the raw bar range.
    if long_side:
        position.extreme = max(position.extreme, bar.high)
        trade.mae = min(trade.mae, bar.low - trade.entry_price)
        trade.mfe = max(trade.mfe, bar.high - trade.entry_price)
    else:
        position.extreme = min(position.extreme, bar.low)
        trade.mae = min(trade.mae, trade.entry_price - bar.high)
        trade.mfe = max(trade.mfe, trade.entry_price - bar.low)

    # 1) Stop first (pessimistic when a bar contains both stop and target).
    stop_hit = bar.low <= trade.stop_price if long_side else bar.high >= trade.stop_price
    if stop_hit:
        reason = ExitReason.ATR_TRAIL if position.trail_active else ExitReason.STOP_LOSS
        equity = _close_position(
            position, bar.time, trade.stop_price, reason, equity, spec, config, result
        )
        return True, equity

    # 2) Fixed target, when the variant uses one.
    if position.target_price is not None:
        target_hit = (
            bar.high >= position.target_price if long_side else bar.low <= position.target_price
        )
        if target_hit:
            equity = _close_position(
                position, bar.time, position.target_price, ExitReason.TARGET, equity, spec,
                config, result,
            )
            return True, equity

    # 3) Break-even and trailing, on the closed bar, favorable direction only.
    r_distance = trade.risk_per_unit
    if r_distance > 0:
        move = (bar.close - trade.entry_price) if long_side else (trade.entry_price - bar.close)
        r_now = move / r_distance

        if p.be_trigger_r > 0 and not position.be_applied and r_now >= p.be_trigger_r:
            candidate = trade.entry_price
            if (long_side and candidate > trade.stop_price) or (
                not long_side and candidate < trade.stop_price
            ):
                trade.stop_price = candidate
                position.be_applied = True

        if r_now >= p.trail_activate_r and trade.atr_at_signal > 0:
            offset = p.trail_atr_mult * trade.atr_at_signal
            candidate = (
                position.extreme - offset if long_side else position.extreme + offset
            )
            if (long_side and candidate > trade.stop_price) or (
                not long_side and candidate < trade.stop_price
            ):
                trade.stop_price = candidate
                position.trail_active = True

    # 4) Regime invalidation — only the OPPOSITE trend forces an exit (spec §8).
    opposite = Regime.TREND_DOWN if long_side else Regime.TREND_UP
    if regime is opposite:
        equity = _close_position(
            position, bar.time, bar.close, ExitReason.REGIME_INVALIDATION, equity, spec,
            config, result,
        )
        return True, equity

    # 5) Time exit.
    if position.bars_held >= p.max_bars_in_trade:
        equity = _close_position(
            position, bar.time, bar.close, ExitReason.TIME_EXIT, equity, spec, config, result
        )
        return True, equity

    # 6) Optional session exit.
    if config.operational.session_exit_enabled and not sessions.is_permitted(bar.time):
        equity = _close_position(
            position, bar.time, bar.close, ExitReason.SESSION_EXIT, equity, spec, config, result
        )
        return True, equity

    # 7) Overnight swap.
    day_key = bar.time.toordinal()
    if position.last_swap_day < 0:
        position.last_swap_day = day_key
    elif day_key > position.last_swap_day:
        nights = day_key - position.last_swap_day
        swap_rate = spec.swap_long if long_side else spec.swap_short
        equity += swap_rate * trade.lots * nights
        trade.costs -= swap_rate * trade.lots * nights
        position.last_swap_day = day_key

    return False, equity


def _close_position(
    position: _OpenPosition,
    exit_time: datetime,
    exit_level: float,
    reason: ExitReason,
    equity: float,
    spec: BrokerSpec,
    config: StrategyConfig,
    result: BacktestResult,
) -> float:
    """Realize the position, applying exit slippage adversely, and record the trade."""
    trade = position.trade
    long_side = trade.direction is Direction.LONG
    slip = config.execution.slippage_points_exit * spec.point
    exit_price = exit_level - slip if long_side else exit_level + slip

    move = (exit_price - trade.entry_price) if long_side else (trade.entry_price - exit_price)
    pnl = move * _value_per_price_unit(trade.lots, spec)

    trade.exit_time = exit_time
    trade.exit_price = exit_price
    trade.exit_reason = reason
    trade.pnl = pnl
    trade.exit_slippage = slip
    # Record the transaction cost actually paid. The spread and slippage are
    # charged by adjusting the fill prices, so without this line `total_costs`
    # would report 0.00 while real money was being spent - which is exactly the
    # kind of understated cost figure mandate §41 warns about.
    trade.costs += (trade.entry_slippage + slip) * _value_per_price_unit(trade.lots, spec)
    trade.bars_held = position.bars_held
    r_distance = trade.risk_per_unit
    trade.r_multiple = (move / r_distance) if r_distance > 0 else 0.0

    result.trades.append(trade)
    return equity + pnl


def state_of(machine: SetupMachine) -> SetupState:
    """Small accessor used by tests and telemetry."""
    return machine.state
