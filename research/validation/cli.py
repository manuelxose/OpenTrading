"""Command-line entry point for the XAU_RPB research pipeline.

    python -m research.validation.cli data-quality  --data <csv>
    python -m research.validation.cli baseline      --data <csv>
    python -m research.validation.cli sensitivity   --data <csv>
    python -m research.validation.cli walk-forward  --data <csv>
    python -m research.validation.cli monte-carlo   --data <csv>
    python -m research.validation.cli cost-stress   --data <csv>
    python -m research.validation.cli full          --data <csv>

Every command requires real market data. **No command fabricates a dataset**: with
no `--data` the tool reports what is missing and exits non-zero, because a report
generated from invented bars would be worse than no report (mandate §53).

Every run writes a config snapshot (spec version, config hash, data hash, cost
model) so any number it prints can be reproduced later (mandate §51).
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from typing import Any

from research.strategies.xau_rpb.backtest import run_backtest
from research.strategies.xau_rpb.config import StrategyConfig
from research.strategies.xau_rpb.data import load_ohlc_csv, validate_bars
from research.strategies.xau_rpb.sessions import us_dst_broker_offset
from research.strategies.xau_rpb.types import BrokerSpec

from .gates import evaluate_gates
from .metrics import compute_metrics, group_by, side_breakdown, yearly_breakdown
from .monte_carlo import block_bootstrap, sequence_bootstrap
from .overfitting import TrialLedger, deflated_sharpe_ratio
from .splits import chronological_split, walk_forward_windows
from .sweeps import (
    execution_stress,
    parameter_stability,
    parameter_sweep,
    run_config,
    summarize_surface,
    walk_forward,
)

# A DEFAULT broker profile for research runs. It is not a claim about any venue:
# the live EA reads every value from the server (spec §10). Override with --spec.
DEFAULT_SPEC = BrokerSpec(
    symbol="XAUUSD", point=0.01, digits=2, tick_value=1.0, tick_size=0.01,
    lot_size=100.0, min_lot=0.01, max_lot=50.0, lot_step=0.01,
    stop_level_points=10.0, freeze_level_points=0.0,
)

# The research neighbourhoods of spec §14 — deliberately small and defensible.
DEFAULT_GRID: dict[str, tuple[float, ...]] = {
    "adx_trend_min": (18.0, 20.0, 22.0, 25.0),
    "sl_atr_mult": (1.5, 2.0, 2.5),
    "breakout_buffer_atr": (0.05, 0.10, 0.15, 0.20),
    "entry_score_threshold": (6, 7, 8),
}

BANNER = """
================================================================================
 XAU_RPB research pipeline
 STATUS: the strategy has NOT been statistically qualified.
 Any figure below is HISTORICAL SIMULATION under the stated cost model.
 It is not an expectation of future performance.
================================================================================
"""


def _broker_offset(args: argparse.Namespace):
    """Resolve --broker-offset into a constant or a per-timestamp callable.

    Default is ``us-dst``: MetaQuotes-style servers (IC Markets included) sit at
    UTC+2 in winter and UTC+3 in summer, so a constant misplaces every session
    boundary for half the year.
    """
    value = str(getattr(args, "broker_offset", "us-dst")).strip().lower()
    if value in ("us-dst", "auto"):
        return us_dst_broker_offset
    return float(value)


def _load(path: str) -> tuple[list, dict[str, Any]]:
    bars = load_ohlc_csv(path)
    if not bars:
        raise SystemExit(f"error: no usable bars parsed from {path}")
    report = validate_bars(bars, expected_interval_minutes=15, source=path)
    return bars, {"data_sha256": report.data_sha256, "bars": len(bars)}


def _snapshot(config: StrategyConfig, extra: dict[str, Any], out_dir: Path) -> Path:
    """Persist everything needed to reproduce this run (mandate §51)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    path = out_dir / f"run_{stamp}_{config.config_hash()}.json"
    payload = {
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "spec_version": config.spec_version,
        "config_hash": config.config_hash(),
        "config": config.to_dict(),
        **extra,
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def cmd_data_quality(args: argparse.Namespace) -> int:
    bars = load_ohlc_csv(args.data)
    report = validate_bars(bars, expected_interval_minutes=args.interval, source=args.data)
    print(report.summary())
    if not report.is_clean:
        print("\nDATA IS NOT CLEAN. Fix the defects above before trusting any backtest.")
        return 1
    if report.span_years < 5.0:
        print(
            f"\nWARNING: {report.span_years:.2f} years of history is below the 5-year "
            "minimum in the mandate (§31). Conclusions will be weakly supported."
        )
    return 0


def _config_for(args: argparse.Namespace) -> StrategyConfig:
    config = StrategyConfig()
    if getattr(args, "research_reset_kill", False):
        config = replace(
            config, risk=replace(config.risk, research_auto_reset_hard_kill=True)
        )
    return config


def cmd_baseline(args: argparse.Namespace) -> int:
    print(BANNER)
    bars, meta = _load(args.data)
    config = _config_for(args)
    if config.risk.research_auto_reset_hard_kill:
        print("NOTE: --research-reset-kill is ON. The hard drawdown kill is rebased")
        print("      each year so the WHOLE sample can be measured. Production")
        print("      behaviour is unchanged: there the kill latches until an")
        print("      operator resets it.")
        print()
    result = run_backtest(bars, config, DEFAULT_SPEC, initial_equity=args.equity,
                          broker_utc_offset_hours=_broker_offset(args))
    metrics = compute_metrics(result.trades, result.equity_curve, args.equity)

    print("BASELINE (unoptimized seeds, spec §14 defaults)")
    print(f"  spec version : {config.spec_version}")
    print(f"  config hash  : {config.config_hash()}")
    print(f"  data sha256  : {meta['data_sha256']}  ({meta['bars']} bars)")
    print()
    for key, value in metrics.as_dict().items():
        print(f"  {key:24s}: {value}")

    print("\nREJECTIONS (why signals did not become trades)")
    for reason, count in sorted(result.rejections.items(), key=lambda kv: -kv[1]):
        print(f"  {reason:28s}: {count}")

    if result.trades:
        print("\nLONG / SHORT ATTRIBUTION (mandate §39)")
        sides = side_breakdown(result.trades, result.equity_curve, args.equity)
        for label, m in (("LONG", sides.long), ("SHORT", sides.short),
                         ("COMBINED", sides.combined)):
            pf = "n/a" if m.profit_factor is None else f"{m.profit_factor:.3f}"
            print(f"  {label:9s} trades={m.trades:4d} PF={pf:>6s} "
                  f"expectancy_R={m.expectancy_r:+.4f} net={m.net_profit:+.2f}")

        print("\nYEAR-BY-YEAR (mandate §40)")
        for year in yearly_breakdown(result.trades):
            pf = "n/a" if year.profit_factor is None else f"{year.profit_factor:.3f}"
            print(f"  {year.year}  trades={year.trades:4d} PF={pf:>6s} "
                  f"net={year.net_profit:+12.2f} share={year.contribution_pct:+6.1f}%")

        print("\nEXIT REASONS")
        for group in group_by(result.trades, "exit_reason"):
            print(f"  {group.label:24s} n={group.trades:4d} "
                  f"net={group.net_profit:+12.2f} expectancy_R={group.expectancy_r:+.3f}")

    snapshot = _snapshot(config, {"data": meta, "metrics": metrics.as_dict()},
                         Path(args.out))
    print(f"\nconfig snapshot -> {snapshot}")
    return 0


def cmd_sensitivity(args: argparse.Namespace) -> int:
    print(BANNER)
    bars, meta = _load(args.data)
    config = StrategyConfig()
    ledger = TrialLedger(Path(args.out) / "trials.json")

    points = parameter_sweep(bars, config, DEFAULT_SPEC, DEFAULT_GRID,
                             initial_equity=args.equity)
    for point in points:
        ledger.record(
            config_hash=point.config_hash, params=point.params,
            profit_factor=point.profit_factor, sharpe=point.metrics.sharpe,
            net_return_pct=point.metrics.net_return_pct,
            trades=point.metrics.trades, partition="FULL",
        )
    ledger.flush()

    surface = summarize_surface(points)
    print("PARAMETER SENSITIVITY (mandate §35 — looking for a plateau, not a peak)")
    print(surface.summary())
    print(f"\n{ledger.summary()}")

    best = max((p for p in points if p.metrics.sharpe is not None),
               key=lambda p: p.metrics.sharpe or 0.0, default=None)
    if best and best.metrics.sharpe is not None:
        dsr = deflated_sharpe_ratio(
            best.metrics.sharpe, trials=ledger.count,
            variance_of_sharpes=ledger.sharpe_variance(),
            sample_length=max(2, best.metrics.trades),
        )
        print("\nDEFLATED SHARPE (mandate §36)")
        print(f"  best observed Sharpe : {best.metrics.sharpe:.4f}")
        print(f"  trials               : {ledger.count}")
        print(f"  deflated Sharpe prob : {'n/a' if dsr is None else f'{dsr:.4f}'}")
        if dsr is not None and dsr < 0.95:
            print("  -> NOT distinguishable from the best of many noisy trials.")

    _snapshot(config, {"data": meta, "surface": asdict(surface)}, Path(args.out))
    return 0


def cmd_walk_forward(args: argparse.Namespace) -> int:
    print(BANNER)
    bars, meta = _load(args.data)
    config = StrategyConfig()

    for anchored in (False, True):
        windows = walk_forward_windows(
            bars, train_months=args.train_months, test_months=args.test_months,
            anchored=anchored,
        )
        label = "ANCHORED" if anchored else "ROLLING"
        print(f"\n{label} WALK-FORWARD (mandate §34): {len(windows)} windows")
        if not windows:
            print("  insufficient history for even one window")
            continue

        results = walk_forward(windows, config, DEFAULT_SPEC, DEFAULT_GRID,
                               initial_equity=args.equity)
        for r in results:
            is_pf = ("n/a" if r.in_sample.profit_factor is None
                     else f"{r.in_sample.profit_factor:.2f}")
            oos_pf = ("n/a" if r.out_of_sample.profit_factor is None
                      else f"{r.out_of_sample.profit_factor:.2f}")
            deg = "n/a" if r.degradation_pct is None else f"{r.degradation_pct:+.1f}%"
            print(f"  {r.window.describe()}")
            print(f"      selected={r.selected_params} IS_PF={is_pf} "
                  f"OOS_PF={oos_pf} degradation={deg}")

        stability = parameter_stability(results)
        if stability:
            print(f"\n  PARAMETER STABILITY ({label})")
            for name, stats in stability.items():
                print(f"    {name:24s} range=[{stats['min']:g}, {stats['max']:g}] "
                      f"cv={stats['coefficient_of_variation']:.3f}")
            print("    A parameter whose selection swings across its whole research")
            print("    range is unstable even when aggregate P&L looks acceptable.")

    _snapshot(config, {"data": meta}, Path(args.out))
    return 0


def cmd_monte_carlo(args: argparse.Namespace) -> int:
    print(BANNER)
    bars, meta = _load(args.data)
    config = StrategyConfig()
    result = run_backtest(bars, config, DEFAULT_SPEC, initial_equity=args.equity,
                          broker_utc_offset_hours=_broker_offset(args))
    if not result.trades:
        print("no trades produced; Monte Carlo needs a realized trade list")
        return 1

    for family in (
        sequence_bootstrap(result.trades, initial_equity=args.equity,
                           iterations=args.iterations),
        block_bootstrap(result.trades, initial_equity=args.equity,
                        iterations=args.iterations, block_size=args.block_size),
    ):
        print(f"\n{family.summary()}")

    _snapshot(config, {"data": meta}, Path(args.out))
    return 0


def cmd_cost_stress(args: argparse.Namespace) -> int:
    print(BANNER)
    bars, meta = _load(args.data)
    config = StrategyConfig()

    print("EXECUTION COST STRESS (mandate §37 family 3, §41)")
    print("The strategy is RE-EXECUTED under each scenario: a wider spread changes")
    print("which setups pass the filter, not merely what they earn.")

    modes = (
        (
            False,
            "FILTER-ACTIVE (operational realism)",
            [
                "The spread filter stays fixed, so widening spreads progressively lock",
                "the strategy out. Falling trade counts here are the system declining",
                "bad conditions - correct behaviour, but it measures the FILTER, not",
                "the edge.",
            ],
        ),
        (
            True,
            "COST-ONLY (edge sensitivity)",
            [
                "Spread thresholds scale with the multiplier so the SAME setups still",
                "qualify and only pay more. This is the variant the acceptance gate",
                "needs: it answers whether the EDGE survives worse costs.",
            ],
        ),
    )
    for hold, title, note_lines in modes:
        print()
        print(title)
        for line in note_lines:
            print(f"  {line}")
        print()
        header = f"  {'scenario':46s} {'trades':>7s} {'PF':>8s} {'net %':>10s} {'maxDD %':>9s}"
        print(header)
        print("  " + "-" * 84)
        for scenario in execution_stress(bars, config, DEFAULT_SPEC,
                                         commission_per_lot=args.commission,
                                         initial_equity=args.equity,
                                         hold_filter_constant=hold):
            m = scenario.metrics
            pf = "n/a" if m.profit_factor is None else f"{m.profit_factor:.3f}"
            print(f"  {scenario.label:46s} {m.trades:7d} {pf:>8s} "
                  f"{m.net_return_pct:>10.2f} {m.max_drawdown_pct:>9.2f}")

    _snapshot(config, {"data": meta}, Path(args.out))
    return 0


def cmd_full(args: argparse.Namespace) -> int:
    """The complete pipeline, ending in the frozen acceptance gates."""
    print(BANNER)
    bars, meta = _load(args.data)
    config = StrategyConfig()

    split = chronological_split(bars)
    print("TEMPORAL PARTITIONS (mandate §33)")
    print(split.describe())

    development = run_config(split.development.bars, config, DEFAULT_SPEC,
                             initial_equity=args.equity)
    final_oos = run_config(split.final_oos.bars, config, DEFAULT_SPEC,
                           initial_equity=args.equity)

    # The gate asks whether the EDGE survives 1.5x costs, so the filter is held
    # constant; otherwise the strategy simply stops trading and the gate becomes
    # unmeasurable rather than informative.
    stress = execution_stress(bars, config, DEFAULT_SPEC,
                              spread_multipliers=(1.5,), slippage_points=(0.0,),
                              initial_equity=args.equity, hold_filter_constant=True)
    stress_pf = stress[0].metrics.profit_factor if stress else None

    oos_run = run_backtest(split.final_oos.bars, config, DEFAULT_SPEC,
                           initial_equity=args.equity)
    mc_p95 = None
    if oos_run.trades:
        mc = block_bootstrap(oos_run.trades, initial_equity=args.equity, iterations=2000)
        mc_p95 = mc.p95_drawdown

    years = yearly_breakdown(oos_run.trades)
    max_year = max((abs(y.contribution_pct) for y in years), default=None)

    report = evaluate_gates(
        final_oos,
        is_profit_factor=development.profit_factor,
        spread_stress_pf=stress_pf,
        monte_carlo_p95_dd=mc_p95,
        max_year_contribution_pct=max_year,
    )
    print("\nACCEPTANCE GATES (mandate §43/§44 — frozen before results were seen)")
    print(report.summary())

    _snapshot(config, {"data": meta, "qualification": report.qualification.value},
              Path(args.out))
    return 0 if report.qualification.value != "REJECTED" else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="research.validation.cli",
        description="XAU_RPB research and validation pipeline",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    commands = {
        "data-quality": cmd_data_quality,
        "baseline": cmd_baseline,
        "sensitivity": cmd_sensitivity,
        "walk-forward": cmd_walk_forward,
        "monte-carlo": cmd_monte_carlo,
        "cost-stress": cmd_cost_stress,
        "full": cmd_full,
    }
    for name, handler in commands.items():
        p = sub.add_parser(name)
        p.add_argument("--data", required=True, help="M15 OHLC CSV (real market data)")
        p.add_argument("--equity", type=float, default=100_000.0)
        p.add_argument("--out", default="research/reports/xau_rpb")
        p.add_argument("--interval", type=int, default=15)
        p.add_argument("--iterations", type=int, default=2000)
        p.add_argument("--block-size", type=int, default=10)
        p.add_argument("--commission", type=float, default=0.0)
        p.add_argument("--train-months", type=int, default=24)
        p.add_argument("--test-months", type=int, default=6)
        p.add_argument(
            "--broker-offset", default="us-dst",
            help="server UTC offset: a number, or 'us-dst' (UTC+2 winter / +3 summer)",
        )
        p.add_argument(
            "--research-reset-kill", action="store_true",
            help="RESEARCH ONLY: rebase the hard-drawdown kill each year so a latched "
                 "kill cannot truncate the sample. Production keeps the kill latched.",
        )
        p.set_defaults(handler=handler)
    return parser


def main(argv: list[str] | None = None) -> int:
    # The reports contain section marks and arrows; a Windows console defaults to
    # cp1252 and would mangle them.
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(
            "\nThis pipeline requires REAL XAUUSD M15 history. It will not invent a "
            "dataset: a report built on fabricated bars is worse than no report.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
