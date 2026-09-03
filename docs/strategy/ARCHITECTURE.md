# XAU_RPB — Architecture

How the strategy is decomposed, and why the boundaries fall where they do.

Authority: [`ADR-0027`](../ADR/0027-standalone-xauusd-rpb-expert-advisor.md).
Contract: [`XAUUSD_RPB_SPEC.md`](XAUUSD_RPB_SPEC.md).

---

## 1. Two implementations, one specification

```
        docs/strategy/XAUUSD_RPB_SPEC.md          <- the single source of truth
                        |
        +---------------+----------------+
        |                                |
  research/strategies/xau_rpb/     mt4/Experts/XauRpbEA.mq4
  (CANONICAL, Python)              (MIRROR, MQL4)
        |                                |
        +----------- tests/parity/ ------+
                 signal parity holds them together
```

The Python package is canonical: it is where the strategy is defined, tested and
researched. The MQL4 EA is a mirror that must agree with it. **Divergence is a
defect**, and the parity fixtures exist to make it visible rather than to make it
unlikely.

This duplication is a real cost, accepted deliberately in ADR-0027 because the
mandate requires an EA that runs on MetaTrader with no Python present. Any spec
change must be applied to both sides in the same change set.

### Relationship to the rest of the repository

`QuantBridgeEA.mq4` remains execution-only under INV-5 — nothing here changes that.
`XauRpbEA.mq4` is a separate, standalone artifact that never speaks the ADR-0020
protocol and is never driven by the Core. INV-5's scope narrows from "MQL4" to "the
QuantBridge execution path"; the invariants file must be read together with
ADR-0027.

INV-1 is untouched: **no LLM participates in this strategy at all.** Every rule is
deterministic arithmetic over closed bars.

## 2. Layering

The dependency direction is strict, and it is what makes the strategy testable
without a broker, a clock or a network:

```
  types.py        value objects; no I/O, no clock, no broker
      ^
  indicators.py   pure functions over price arrays
      ^
  regime.py       H1 classification          config.py   parameters (4 categories)
  state_machine.py M15 setup transitions          ^
  scoring.py      signal quality                  |
      ^                                           |
  sizing.py  risk_limits.py  sessions.py  news.py |
      ^                                           |
  backtest.py     execution simulation ------------
      ^
  research/validation/   metrics, gates, WFO, Monte Carlo, PBO
```

Nothing below `backtest.py` reads a clock or performs I/O. Every input that
participates in a decision is passed in explicitly, which is what makes INV-3
(point-in-time correctness) checkable: there is no hidden channel through which a
future bar could arrive.

## 3. Module responsibilities

### Strategy (`research/strategies/xau_rpb/`)

| Module | Responsibility | Key invariant |
|---|---|---|
| `types.py` | `Bar`, `BrokerSpec`, `Trade`, enums | Frozen value objects; `BrokerSpec.is_valid()` gates everything |
| `config.py` | Parameters in 4 categories; config hashing | `with_research()` is the only ergonomic override path, so a sweep cannot reach risk policy |
| `indicators.py` | EMA, TR, ATR, ADX, ER, ATR-percentile | Exact spec definitions, not library defaults; `nan` means "undefined", never zero |
| `regime.py` | H1 classification | Evaluation order is normative; HIGH_VOLATILITY dominates trend |
| `state_machine.py` | M15 setup transitions | Total and ordered; every transition records a reason |
| `scoring.py` | 7-factor, max-9 score | Can only make a setup ineligible; never substitutes for a hard gate |
| `sizing.py` | Broker-aware lots | Always floors; never rounds up to `min_lot` |
| `risk_limits.py` | Kill switches | Blocks entries; never liquidates; hard kill latches |
| `sessions.py` | Broker time → UTC → sessions | Offset is an input, never a guess |
| `news.py` | Frozen-CSV blackout | Fails closed when required and unreadable |
| `backtest.py` | Event-driven simulation | Signal on close, fill on next open; stop before target |
| `data.py` | Loading + §32 integrity report | Never fabricates; reports defects |
| `parity.py` | Fixtures and goldens | Stable seeds, reproducible across processes |

### MQL4 (`mt4/Include/xau_rpb/`)

Ten header-guarded modules mirroring the above: `Config`, `BrokerSpec`,
`Indicators`, `Regime`, `SetupMachine`, `Risk`, `Sessions`, `News`, `Execution`,
`Telemetry`. `XauRpbEA.mq4` is composition and event routing only — it holds no
strategy rules of its own.

**Order submission funnels through `Execution.mqh` alone.** A test fails the build
if `OrderSend(` appears anywhere else, which is what keeps the §9 guards from being
bypassed by a future edit.

### Validation (`research/validation/`)

| Module | Responsibility |
|---|---|
| `metrics.py` | §42 metric set, side/year/group attribution |
| `gates.py` | §43 acceptance gates, §44 rejection conditions, qualification |
| `splits.py` | Chronological partitions, walk-forward windows, `OosLedger` |
| `sweeps.py` | Parameter sweeps, plateau summary, cost stress, walk-forward |
| `monte_carlo.py` | Sequence and block bootstrap |
| `overfitting.py` | PBO/CSCV, Deflated Sharpe, `TrialLedger` |
| `cli.py` | The pipeline entry point |

## 4. Event model (spec §27, §58)

Work is done at the cheapest cadence that is still correct:

```
per tick        manage the open position: trailing, break-even
                (the protective stop itself lives broker-side)

new CLOSED H1   recompute the regime  (~1 ms, 24x/day)

new CLOSED M15  advance the setup machine; on SIGNAL_READY apply
                score -> guards -> sizing -> submission
```

Ordering is normative: when an H1 and M15 close coincide, the **regime updates
first**, then the M15 logic runs against it.

Indicator windows are recomputed wholesale on each new bar rather than updated
incrementally. That costs about a millisecond an hour and removes an entire class
of incremental-state bugs that would break parity silently — the right trade for a
system whose correctness matters more than its microseconds.

## 5. Separation of concerns that carry weight

**Signal validity vs. order executability.** A valid signal that fails a broker
guard is rejected and logged with a reason code. It is never rescued by relaxing
the signal, widening the stop, or increasing risk.

**Risk vs. alpha.** Sizing takes the stop distance and the risk budget; it never
sees the score. The score never sees the equity. This is enforced by the type
signatures, not by convention.

**Policy vs. research.** The four parameter categories are separate structs. A
sweep that could reach `RiskPolicyParams` would be a design error, not a mistake.

## 6. Failure model

Fail closed, everywhere (spec §15):

| Failure | Response |
|---|---|
| Invalid/missing broker spec | Refuse to start; no defaults substituted |
| Non-finite indicator, ATR ≤ 0 | No trade; setup reset |
| Insufficient history | No trade |
| Unreadable news file (when required) | Block all new entries |
| Spread beyond threshold | Reject, log `SPREAD_TOO_WIDE` |
| Margin check fails | Reject, log `INSUFFICIENT_MARGIN` |
| Min lot exceeds risk budget | **No trade** — never a bigger trade |
| >1 position found on restart | `SAFE_MODE`: manage only, alert |
| Transient broker error | Bounded retry (3), never widening the stop |
| Terminal broker error | Abandon the setup, log the code |

## 7. State and recovery

The EA's authoritative state is the broker's order book, not memory. On every
init it enumerates open orders, matches by **magic number and comment prefix**, and
resumes management without re-entering.

One honest gap: the **signal-time ATR is not recoverable** from the broker, so
trailing resumes on a freshly computed ATR. Immediately after a restart, trail
distances may differ slightly from an uninterrupted run. This is documented rather
than hidden behind a fabricated value.

## 8. Telemetry

Append-only CSV, one row per decision, with the full feature vector, score
breakdown, sizing inputs, and reject or exit reason. It answers "why did it not
trade?" directly — the counterfactual is recorded, not inferred.

Telemetry never influences a decision, and a telemetry failure never blocks one.
