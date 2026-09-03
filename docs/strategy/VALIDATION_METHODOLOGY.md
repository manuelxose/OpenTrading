# XAU_RPB — Validation Methodology

How this strategy would be proven or rejected, and what has actually been done so
far. For the current status, see [`RESEARCH_REPORT.md`](RESEARCH_REPORT.md).

The methodology is written to make **rejection easy**. A research process that can
only confirm is not a research process, and the mandate is explicit: rejecting a
false alpha is a successful outcome (§67).

---

## 1. Order of work

Correctness first, optimization last (mandate §60):

```
formal specification -> deterministic implementation -> unit tests -> signal parity
  -> baseline backtest -> cost modelling -> parameter sensitivity -> validation
  -> optimization -> final OOS -> stress tests
```

Never the inverse (optimize, pick a pretty curve, retrofit an explanation).

## 2. Data requirements (mandate §31, §32)

| Requirement | Target |
|---|---|
| Instrument | XAUUSD M15 (H1 derived by aggregation) |
| Minimum history | 5 years |
| Preferred history | 8–10 years |
| Preferred content | bid/ask or tick data with per-bar spread |
| Minimum content | OHLC + a spread column |

The history must span materially different environments: low and high volatility,
the 2020 dislocation, the 2022 inflation shock, Fed hiking and cutting cycles,
strong gold trends and long consolidations. A strategy validated only on a bull
trend has been validated on one regime, not on a market.

**Data quality is a gate, not a formality.** `research/validation/cli.py
data-quality` produces the §32 report and exits non-zero when it finds duplicate
timestamps, out-of-order bars, impossible OHLC, non-positive prices or negative
spreads. Gaps are reported with weekend gaps identified separately, since those are
expected market structure rather than defects.

Every run records a SHA-256 of the bar series. A result that cannot name its data
hash is not reproducible.

## 3. Temporal partitions (mandate §33)

Never shuffled. Never sampled. Strictly chronological:

```
|<------- DEVELOPMENT (55%) ------->|<-- VALIDATION (20%) -->|<-- FINAL OOS (25%) -->|
```

The **final OOS partition is a one-shot resource**. It stays untouched until the
rules are frozen, the parameter regions are chosen and the implementation is
complete. `research/validation/splits.py::OosLedger` records every consultation
with its config hash; once a second distinct configuration has looked at it, the
ledger reports the partition as **SPENT** and its results must thereafter be
described as in-sample research. This is a tripwire that leaves a record, not a
lock.

## 4. Walk-forward (mandate §34)

Both variants are run and compared:

- **Rolling** — 24 months train / 6 months test, sliding.
- **Anchored** — fixed start, growing train, same 6-month test.

The headline output is **not** aggregate P&L. It is **parameter stability**:
`parameter_stability()` reports the min, max, mean, standard deviation and
coefficient of variation of every selected parameter across windows. A system whose
selected ADX threshold jumps 17 → 31 → 12 → 39 is unstable even if the summed P&L
is positive; a system that repeatedly selects from within 18–25 is interesting.

Per-window IS→OOS degradation is reported for every window, not just in aggregate.

## 5. Parameter sensitivity (mandate §35)

The objective is a **plateau, not a peak**.

```
Bad  : 2.37 ATR excellent, 2.30 poor, 2.40 poor      <- a spike; curve fitting
Good : 1.8 - 2.3 ATR all acceptable                  <- a region; possibly real
```

`summarize_surface()` therefore reports the fraction of the neighbourhood that is
profitable and its **median** profit factor, and flags `is_plateau` when at least
70% of the region works with a median PF ≥ 1.0. The best-performing combination is
printed only for completeness, with an explicit note that selecting it is the
overfitting mechanism the mandate forbids.

Only `RESEARCH` parameters can be swept. `StrategyConfig.with_research()` is the
only override path, so a sweep **structurally cannot** touch the risk mandate.

## 6. Overfitting controls (mandate §36)

- **Every trial is recorded**, including the losers (`TrialLedger`). The trial
  count feeds the Deflated Sharpe Ratio, so under-recording it directly inflates
  apparent significance.
- **PBO via CSCV** — the performance matrix is split into complementary IS/OOS
  combinations; PBO is the frequency with which the IS-best configuration lands in
  the bottom half OOS. PBO near 0.5 means the selection procedure carries no
  information.
- **Deflated Sharpe Ratio** — corrects the observed Sharpe for the number of
  trials, skew and kurtosis. Below ~0.95 the result is not distinguishable from
  the best of many noisy trials.

Reported alongside: number of strategy variants tested, number of parameter
combinations, best IS result, **median** IS result, and the corresponding OOS
result.

## 7. Monte Carlo (mandate §37)

| Family | Question it answers |
|---|---|
| Trade-sequence bootstrap | Was the observed drawdown an artefact of ordering? |
| Block bootstrap | The same, preserving clustering — losses arrive together, and IID resampling hides exactly that |
| Execution perturbation | Does the edge survive worse fills? |
| Parameter jitter | Is this a plateau or a spike? |

Percentiles use nearest-rank, so a reported P95 is a value that actually occurred.
Outputs: drawdown distribution (P50/P95/P99/worst), return distribution, losing
streak distribution, probability of loss, and risk of ruin.

The block bootstrap is usually the more honest tail and is the one wired into the
acceptance gates.

## 8. Cost stress (mandate §37, §41)

Scenarios are **re-executed**, never rescaled. This matters: a wider spread changes
*which setups pass the spread filter at all*, not merely what the taken trades
earn. Rescaling a stored P&L series would systematically understate the damage.

```
spread multiplier : 1.00x  1.25x  1.50x  2.00x
slippage          : +0     +1     +2     +3 points
commission        : configurable per lot
swap              : charged per night held, from the broker spec
```

All reported performance is **net** of spread, slippage, commission and swap.
Gross theoretical performance is never presented as strategy performance.

## 9. Multi-broker portability (mandate §38)

At least three independent broker feeds, comparing signal timing, trade direction,
profit factor, expectancy, drawdown and realized costs. Per broker and per period,
the following are captured: `Digits`, `Point`, `TickSize`, `TickValue`, `LotSize`,
`MinLot`, `LotStep`, `MaxLot`, `StopLevel`, `FreezeLevel`, spread, `SwapLong`,
`SwapShort`, `ProfitCalcMode`, `MarginCalcMode`.

An edge that exists on one feed and disappears on two others is a data artefact,
and `evaluate_gates(broker_profit_factors=...)` rejects it automatically.

## 10. Attribution (mandate §39, §40)

Always reported separately, never only in aggregate:

- **LONG / SHORT / COMBINED.** A combined curve must not hide a structurally
  broken side. If one side fails, that is reported — not optimized until it works.
- **Year by year**, with each year's share of total profit.
- **By session** (London / overlap / New York / Asian / rollover).
- **By regime, by ATR percentile, by exit reason.**

Automatic flags: any single year contributing more than 50% of total profit; fewer
than five trades explaining the majority of profit.

## 11. Acceptance gates (mandate §43)

Frozen in `research/validation/gates.py` and pinned by tests, so that relaxing one
is a visible, reviewable diff rather than a quiet edit after a bad run.

| Gate | Minimum | Desired |
|---|---|---|
| OOS net profit factor | ≥ 1.25 | 1.35–1.60 |
| OOS expectancy | > 0 | > 0.10 R/trade |
| OOS max drawdown | ≤ 15% | ≤ 10% |
| Recovery factor | ≥ 1.5 | > 2 |
| Sharpe (net) | > 0.5 | > 0.8 |
| OOS trades | ≥ 200 | 300+ |
| PF degradation IS→OOS | < 30% | < 20% |
| 1.5× spread stress PF | > 1.0 | > 1.15 |
| Monte Carlo P95 drawdown | < 20% | < 15% |

A gate with no input is `NOT_EVALUABLE` — never a silent pass — and any
non-evaluable gate blocks a candidate classification.

## 12. Automatic rejection (mandate §44)

Any one of these returns the strategy to research:

```
OOS PF < 1.10                          OOS expectancy <= 0
OOS max drawdown > 20%                 PF collapse > 40% IS -> OOS
1.5x spread stress PF < 1              parameter neighbourhood predominantly losing
profitable on one broker, losing on others
fewer than 5 trades explain most profit
one year explains > 50% of profit      Monte Carlo P95 drawdown breaches the mandate
survival requires martingale/grid/averaging
performance disappears after realistic costs
```

**These are not relaxed after seeing poor results.** That rule is the entire value
of writing them down in advance.

## 13. Qualification ladder (mandate §61 Phase 13)

Exactly four permitted outcomes — no invented intermediate category:

```
REJECTED · RESEARCH ONLY · FORWARD-TEST CANDIDATE · MICRO-LIVE CANDIDATE
```

## 14. Deployment path (mandate §55)

Even a passing result does not go straight to capital:

```
Research -> Validation -> Final untouched OOS -> MT4 SHADOW mode
  -> Demo forward -> Micro-live -> Controlled scaling
```

The EA ships defaulting to `SHADOW`, which computes every signal, logs every
decision and submits **no orders**. Shadow output is compared against the research
signals before trading is enabled — this is the practical check that the two
implementations agree on live data, not just on fixtures.

## 15. Signal parity (mandate §46)

Given identical OHLC, the Python reference and the MQL4 EA must produce the same
regime, setup state, direction, entry bar and stop distance. Legitimate divergence
is confined to execution simulation (fill price, slippage, broker rejection).

- Fixtures and goldens: `data/fixtures/xau_rpb/*.csv`, `*.golden.json`
- MQL4 harness: `mt4/tests/XauRpbParityHarness.mq4`
- Comparison: `tests/parity/test_signal_parity.py`

CI has no MetaTrader terminal, so the MQL4 comparison **skips** until a `.actual`
file is produced and copied back. The skip message says so explicitly: an
unverified mirror is an open risk, not a passing result. A static correspondence
check (`test_implementation_correspondence.py`) does run in CI and catches the most
likely drift — states, reject codes, transition reasons and parameter defaults
diverging between the two sources.

## 16. Reproducibility (mandate §51)

Every run writes a snapshot containing the spec version, config hash, full
parameter set, data hash, broker profile, cost model and results. A backtest report
without a strategy version and config hash is not evidence.
