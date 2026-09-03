# XAU_RPB — Research Report and Qualification Status

- Strategy: `XAU_RPB` — Regime-Filtered Pullback → Breakout, XAUUSD
- Specification: `XAU_RPB_V1.0.0` ([`XAUUSD_RPB_SPEC.md`](XAUUSD_RPB_SPEC.md))
- Report date: 2026-08-31

---

## FINAL STATUS

```
QUALIFICATION: RESEARCH ONLY  (seed parameters show NO EDGE and would be REJECTED)
```

**Updated 2026-08-31** after connecting to the MetaTrader 4 terminal on this
machine. The strategy has now been **measured on 19.58 years of real IC Markets
XAUUSD M15 data** (448,172 bars, data sha256 `f52256fbbdb200be`).

With the frozen seed parameters the result is negative, and one number settles it:

```
with ZERO transaction costs:  1,108 trades, profit factor 0.992
```

**There is no gross edge to erode.** This is not a viable strategy damaged by
costs — it is a strategy with no measurable edge, which costs then make worse. Per
mandate §44 ("OOS expectancy <= 0", "performance disappears after realistic
costs"), these parameters would be **REJECTED**.

The status stays `RESEARCH ONLY` rather than `REJECTED` for one honest reason: the
mandated research programme — sensitivity, walk-forward, Monte Carlo on real
trades, multi-broker, and a frozen final OOS — has not yet been run on this data.
Rejecting the *strategy family* on a single unoptimized seed run would be as
unrigorous as accepting it on one. What is rejected today is **this parameter
set**, and that is recorded below rather than tuned away.

---

## 1. What was built

| Component | Location | State |
|---|---|---|
| Frozen strategy contract | `docs/strategy/XAUUSD_RPB_SPEC.md` | Complete |
| Canonical implementation (Python) | `research/strategies/xau_rpb/` | Complete, tested |
| Mirror implementation (MQL4) | `mt4/Experts/XauRpbEA.mq4` + `mt4/Include/xau_rpb/` (10 modules) | **Compiles: 0 errors, 0 warnings** |
| Validation & robustness tooling | `research/validation/` | Complete, **run on 19.6 y of real data** |
| Signal-parity harness | `mt4/tests/XauRpbParityHarness.mq4` + `tests/parity/` | Compiles; MQL4 side **not yet run** |
| Architecture decision | `docs/ADR/0027-standalone-xauusd-rpb-expert-advisor.md` | Accepted |
| Documentation | risk policy, validation methodology, broker compatibility, research sources, runbook | Complete |
| MT4 history exporter | `scripts/export_mt4_history.py` | Complete, used |

**223 tests added. 218 pass, 5 skip** (the 5 skips are the MQL4 parity comparisons,
which require a MetaTrader terminal — see §5).

The repository's pre-existing 13 test failures (in `tests/chaos`, `tests/worker`,
`tests/unit/apps`, `tests/unit/config`) were present before this work and are
unchanged; they require the Docker infrastructure stack. **No regressions were
introduced.**

## 2. Tests executed

```bash
uv run pytest tests/unit/strategy tests/unit/validation tests/parity \
              tests/leakage/test_xau_rpb_no_lookahead.py
```

| Suite | Tests | Result |
|---|---|---|
| `tests/unit/strategy/test_indicators.py` | 17 | pass |
| `tests/unit/strategy/test_regime.py` | 15 | pass |
| `tests/unit/strategy/test_state_machine.py` | 19 | pass |
| `tests/unit/strategy/test_sizing.py` | 25 | pass |
| `tests/unit/strategy/test_risk_limits.py` | 13 | pass |
| `tests/unit/strategy/test_sessions_and_news.py` | 19 | pass |
| `tests/unit/validation/test_metrics_and_gates.py` | 27 | pass |
| `tests/unit/validation/test_robustness_tooling.py` | 25 | pass |
| `tests/parity/test_implementation_correspondence.py` | 40 | pass |
| `tests/parity/test_signal_parity.py` | 15 | 10 pass, **5 skip** |
| `tests/leakage/test_xau_rpb_no_lookahead.py` | 8 | pass |

Lint: `ruff check` clean across all added code.

### Leakage guards (the ones that matter most)

Look-ahead makes a worthless strategy look excellent and never announces itself, so
it is attacked structurally rather than by inspection:

- **Prefix invariance** — truncating the series does not change any decision made
  before the cut.
- **Future mutation** — shifting every bar after a cut by up to ±50 price units
  leaves earlier entries byte-identical.
- **Fill timing** — no trade is ever filled at a price from the bar that generated
  its signal; entries anchor to the *next* bar's open.
- **Concurrency** — realized trades never overlap.
- **Warmup** — no trade before indicators are defined.
- **Determinism** — identical inputs produce identical trade lists.

All pass.

## 3. Baseline on real data — RUN 2026-08-31

### Data

| | |
|---|---|
| Source | MT4 IC Markets, `.hst` export via `scripts/export_mt4_history.py` |
| Symbol / digits | `XAUUSD`, 2 digits |
| Bars | **448,172** M15 |
| Range | 2004-06-11 → 2024-01-09 (**19.58 years**, broker server time) |
| Data quality | **CLEAN** — 0 duplicates, 0 out-of-order, 0 impossible OHLC, 0 non-positive prices |
| sha256 | `f52256fbbdb200be` |
| Spread | **MODELLED at 25 points** — MT4 `.hst` files carry no per-bar spread |
| Server offset | **UTC+2 winter / UTC+3 summer**, measured (see §4.5) |

### Result — production kill semantics

| Metric | Value |
|---|---|
| Trades | 148 |
| Profit factor | **0.525** |
| Expectancy | **−0.263 R** |
| Net return | −9.10 % |

**The hard drawdown kill latched in 2012 and blocked the remaining 12 years.** That
is correct production behaviour, but it means this run measured 2006–2012 only. A
research-only yearly rebase (`--research-reset-kill`, never enabled in production)
was added so the full sample could be characterized.

### Result — full sample (research kill rebase)

| Metric | Value |
|---|---|
| Trades | 383 |
| Profit factor | **0.890** |
| Expectancy | **−0.061 R** |
| Net return | −5.36 % |
| Max drawdown | 14.31 % |
| Win rate | 40.2 % |
| Payoff ratio | 1.32 |
| Transaction costs paid | $3,954 |
| Max losing streak | 10 |

Long **PF 0.833** (−$4,126) · Short **PF 0.949** (−$1,233). **Both sides lose** —
this is not a broken side hidden by a working one.

### The decisive test: strip all costs

| Spread | Trades | PF | Net % | Costs |
|---|---|---|---|---|
| **0.0 pts (no cost at all)** | **1,108** | **0.992** | **−1.08 %** | $0 |
| 10 pts | 971 | 0.948 | −7.11 % | $7,506 |
| 15 pts | 728 | 0.911 | −9.11 % | $6,930 |
| 25 pts (baseline) | 383 | 0.890 | −5.36 % | $3,954 |
| 37.5 pts | 134 | 0.546 | −7.12 % | $1,338 |
| 50 pts | 39 | 0.781 | −1.44 % | $666 |

**Profit factor 0.992 with zero costs is the finding.** The signal has no
directional edge before costs are considered at all. The falling trade count also
shows the spread filter progressively locking the strategy out, which is the
filter working as designed.

### Year by year — a clear regime split

Losing every year 2006–2018 (PF mostly 0.3–0.9), then winning 2019–2023
(PF 2.19 / 1.01 / 1.35 / 2.16 / 1.14).

Two readings, and the honest position is that this run cannot separate them:

1. The edge is real but only present in strongly trending gold regimes — plausible
   for a trend-following system, and 2019–2023 was exactly that.
2. Older MT4 back-fill is lower quality than recent history, and the early years
   are partly artefact. The sparse years (2 trades in 2017 and 2018, 1 in 2024)
   support some of this.

Distinguishing them requires the walk-forward and multi-broker work below — it is
**not** grounds for restricting the strategy to post-2019 data, which would be
selecting the sample to fit the result.

### Not yet run on this data

Sensitivity, walk-forward, Monte Carlo on real trades, multi-broker portability
and the frozen final OOS. The tooling is built and verified; these are the next
actions in §7.

## 4. Substantive findings

Three real defects were found and fixed during implementation. Each was caught by a
test or a measurement, not by reading.

### 4.1 The source audit's sizing formula is wrong by 100×

The audit's `CalculateRiskLots` computes `tickSizePrice = tickSizePoints * Point`,
treating `MODE_TICKSIZE` as a count of points. It is a **price** (0.01 on a 2-digit
XAUUSD). Multiplying by `Point` understates every position by `1/Point` — a factor
of 100 on a 2-digit gold feed.

Had this been carried through, every position would have been 1% of its intended
size: the EA would have looked safe while being economically inert, and the error
would likely have been "fixed" later by inflating the risk percentage. Pinned by
`test_sizing.py`, which asserts the economics directly (0.5 lots of a 100 oz
contract risking exactly $500 across a $10 stop).

### 4.2 The breakout reference made the natural entry bar unable to fire

Folding the recovery bar's own high into `breakout_reference` means the bar that
ends the pullback can never exceed the level it must break. The classic
pullback-breakout entry — a strong bar closing back above the structure — was
structurally impossible, and every entry was biased one bar late.

Found by a state-machine test that expected a signal and did not get one. Spec
§5.2/§5.3 were amended: the reference freezes at the pullback structure, and the
recovery bar is itself evaluated.

### 4.3 The spread filter interacts with the spread-stress gate

Mandate §43 asks for "1.5× spread stress PF > 1". But the spread filter is a
cliff: on the smoke fixture, trade count fell 191 → 8 → 0 as the multiplier rose,
so at 1.5× there were no trades and the gate became **unmeasurable rather than
informative**.

`execution_stress()` now runs two modes and both are reported:

- **filter-active** — operational realism; shows the system declining a
  deteriorating venue (correct behaviour, but it measures the filter, not the edge);
- **cost-only** — thresholds scale with the multiplier so the same setups still
  qualify and merely pay more; this is what the gate actually needs.

The `full` pipeline feeds the cost-only variant to the gate.

### 4.5 The broker's UTC offset is not constant — a fixed offset was wrong

`SessionResolver` originally took a **constant** broker UTC offset. Measuring the
real IC Markets M15 history showed that is wrong for half of every year.

The evidence: the bar histogram has **zero bars at server hour 00:00** all year
round, and the week opens Monday 01:00 server. Gold's daily break is 22:00-23:00
UTC in winter and 21:00-22:00 UTC in summer. A server whose break stays fixed in
its own clock while the UTC break moves must itself be moving:

```
IC Markets server = UTC+2 (winter) / UTC+3 (summer), following US DST
```

A constant offset would have misplaced **every session boundary by one hour for
roughly half of each year** — silently, with no error anywhere. `SessionResolver`
now accepts a per-timestamp callable and `us_dst_broker_offset()` implements the
measured rule. This was found by looking at the data, not by reading the code.

### 4.6 A latched kill switch silently truncated the sample

The first real baseline reported 148 trades and stopped producing them after 2012.
The cause was correct production behaviour: the hard drawdown kill **latches**
until an operator resets it (spec §7.2), so once it fired in 2012 the remaining 12
years of data were never traded and never measured.

Correct in production, useless in research. A `--research-reset-kill` option now
rebases the kill yearly so the whole sample can be characterized. Production
semantics are untouched, and any run using it says so in its output.

### 4.7 Reported transaction costs were always zero

`total_costs` read `0.00` on every run while real money was being spent, because
spread and slippage are charged by adjusting the fill price and were never
accumulated into `Trade.costs`. Understating costs is precisely the failure mode
mandate §41 warns about. Now recorded: the baseline pays **$3,954** over 383
trades.

### 4.8 The export tool overwrote one dataset with another

Two MT4 installations on this machine carry the **same server name**
(`ICMarketsSC-Live05`). The exporter named files by symbol/period/server only, so
the 1.17-year dataset silently overwrote the 19.58-year one. The data-folder id is
now part of the filename. This would have been invisible had the 19.6-year history
not been noticed in the log.

### 4.9 Two smaller ones

- **`spread_atr_max` seed was unusable.** Measured typical XAUUSD spread/M15-ATR at
  roughly 0.05–0.12; the initial 0.06 rejected nearly every valid setup. Recalibrated
  to 0.12 as **venue calibration** (documented as such), not as P&L tuning.
- **The parity fixtures were not reproducible.** They seeded from Python's builtin
  `hash()`, which is randomized per process, so "deterministic" fixtures differed
  between runs. Replaced with a SHA-256-derived seed; determinism now verified
  across separate processes.

## 5. Limitations — stated plainly

Three of the original blockers are resolved. What remains is listed honestly.

**Resolved 2026-08-31**

- ~~No market data.~~ 19.58 years of real IC Markets XAUUSD M15 now exported and
  measured.
- ~~The EA has never been compiled.~~ Compiles with **0 errors, 0 warnings**.
- ~~No MetaTrader terminal available.~~ Connected; symbol, digits, server offset
  and history all verified against the live terminal.

**Still open**

1. **MQL4-side signal parity is still unverified.** The harness compiles, but MT4
   cannot run a script from the command line — producing the `.actual` files needs
   one manual drag onto a chart per scenario. The 5 parity tests still skip, and
   say so loudly. **An unverified mirror is an open risk.**
2. **Historical spread is modelled, not observed.** MT4 `.hst` files carry no
   per-bar spread, so the 25-point constant is an assumption. Its impact is
   quantified in §3, which is the right way to handle an assumed parameter — but
   it remains an assumption, and real spreads widen exactly when this strategy
   would want to trade.
3. **Single broker.** All 19.6 years come from one IC Markets feed. Mandate §38
   asks for three independent feeds; an edge visible on one feed and absent on two
   others is a data artefact.
4. **The pre-2019 data is of unknown quality.** Sparse years (2 trades in 2017 and
   2018, 1 in 2024) suggest the older back-fill may be thin or synthesized. This
   directly affects how much weight the 2006–2018 losing stretch should carry.
5. **The 19.6-year dataset ends 2024-01-09.** The second terminal covers
   2025-04-30 → 2026-06-30. There is a gap of roughly 16 months that neither
   dataset covers.
6. **Sensitivity, walk-forward, Monte Carlo and the final OOS have not been run on
   this data.** Only the baseline and the cost study have.
7. **No forward or demo testing.** No shadow-mode run against a live feed.
8. **The execution model is bar-based.** Signal on close, fill on next open, stop
   assumed hit before target within a bar. Conservative, but tick data would
   resolve intrabar sequencing properly.
9. **Swap is modelled per calendar night**, not per broker rollover convention
   (triple Wednesday swaps are not modelled).
10. **The news calendar is empty.** Only a 10-row template exists.

## 6. What is NOT claimed

- **No claim that this strategy has an edge.** The measured result is the opposite:
  profit factor 0.992 with zero costs over 1,108 trades.
- **No claim that it is definitively dead either.** One unoptimized seed run is not
  a rejection of the family — the research programme in §7 is what would settle it.
- No claim about future returns. No annual percentage. No expected profit factor.
- **No claim that the 2019–2023 winning stretch is an edge.** It is an observation
  in one sample, on one broker, and selecting the strategy to that window would be
  fitting the sample.
- No figure from the source audit is inherited as a property of this
  implementation.
- No claim that the MQL4 EA matches the reference — it compiles, but parity is
  unverified.
- No claim of production readiness. The EA defaults to `SHADOW` and submits no
  orders.

## 7. Next actions — evidence-supported only

The first three original blockers are cleared, so the list has changed.

1. **Verify signal parity.** Copy the fixtures into `MQL4/Files/`, run
   `XauRpbParityHarness` once per scenario (5 drags onto a chart), copy the
   `.actual` files back, and run `pytest tests/parity`. **Do nothing else until
   this passes** — every conclusion below assumes the two implementations agree.
2. **Get a second and third broker feed.** The single-feed result cannot
   distinguish "no edge" from "this feed's older history is poor". This is the
   highest-value next data step, and it is cheap: any two demo accounts.
3. **Run sensitivity on the development partition only.** The question is not
   "which parameters win" but "is there a plateau anywhere in the defensible
   neighbourhoods". If the whole surface is below PF 1.0 pre-cost, the family is
   dead and should be recorded as `REJECTED`.
4. **If and only if a plateau exists**, run rolling and anchored walk-forward and
   inspect parameter stability. A plateau that moves every window is not a plateau.
5. **Monte Carlo and cost stress** on the resulting trade list.
6. **Freeze parameters, then consult the final OOS once.** The `OosLedger` records
   it; a second look with different parameters marks it spent.
7. **Apply the gates** via `cli full`. Accept the verdict, including rejection.
8. Only on a pass: shadow mode -> demo forward -> micro-live.

A realistic expectation, stated in advance so it cannot be rationalized later:
**given PF 0.992 with zero costs, step 3 is more likely to end in rejection than
in a plateau.** That is a legitimate and useful outcome.

## 8. Definition of Done

| Item | Status |
|---|---|
| Repository inspected, audit incorporated | Done |
| Strategy mathematically specified | Done |
| Only closed bars generate confirmed signals | Done, tested |
| Deterministic regime engine | Done, tested |
| Deterministic pullback state machine | Done, tested |
| Long and short implemented symmetrically | Done, tested |
| Breakout confirmation (close-based) | Done, tested |
| ATR risk logic, broker-aware sizing | Done, tested |
| Spread / slippage / margin protection | Done, tested |
| Session + DST handling | Done, tested |
| News risk filter (frozen CSV, fails closed) | Done, tested |
| Daily / weekly / hard-DD kill switches | Done, tested |
| Martingale, grid, averaging-down absent | Done, enforced by test |
| Duplicate-order protection, restart recovery | Done (Python tested; MQL4 unverified) |
| Shadow mode | Done (MQL4, unverified) |
| Structured telemetry | Done (MQL4, unverified) |
| Automated tests | Done — 223 added |
| Signal-parity tests | Built and compiling; **MQL4 side not executed** |
| Compiles under MQL4 strict mode | **Done** — 0 errors, 0 warnings |
| Research baseline executed | **Done** — 19.58 y real data, result negative |
| Realistic costs included | **Done** — measured; spread still MODELLED, not observed |
| Temporal validation / walk-forward / Monte Carlo | Implemented; **not yet run on real data** |
| Cost stress | **Done** — six spread levels, see §3 |
| Results reproducible | Config + data hashing in place |
| Documentation complete | Done |
| Known limitations documented | Done — §5 |
| No false production claims | Done |

## 9. Closing note

The mandate's own principle applies: *the project succeeds even if the strategy is
ultimately rejected; shipping an overfit EA because its backtest looked profitable
is the failure.*

Connecting to the terminal turned this from an untested instrument into a measured
one, and the measurement is unfavourable: **profit factor 0.992 before any costs
at all.** That is a far more useful outcome than a flattering curve would have
been, and it arrived before any capital was at risk.

Four additional real defects surfaced only because real data was used — a fixed
broker offset that was wrong half the year, a latched kill switch that hid 12 years
of the sample, transaction costs reported as zero, and an exporter that overwrote
one dataset with another. None of them would have been visible on synthetic
fixtures.

The correct status is **RESEARCH ONLY**, with these seed parameters recorded as
showing no edge. It should stay there until §7 has been carried out.
