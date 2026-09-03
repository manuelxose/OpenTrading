# XAU_RPB — Risk Policy

Authoritative statement of the risk mandate for `XAU_RPB_V1.0.0`. Implemented in
`research/strategies/xau_rpb/{sizing,risk_limits}.py` and
`mt4/Include/xau_rpb/Risk.mqh`; pinned by `tests/unit/strategy/test_sizing.py` and
`test_risk_limits.py`.

**These values are mandate policy, not alpha variables.** They are never swept,
never optimized, and structurally unreachable from a parameter search:
`StrategyConfig.with_research()` is the only override path a sweep can use, and it
cannot touch `RiskPolicyParams`.

---

## 1. First principle

**Risk is independent of signal.** A stronger signal never buys a larger position.
Position size is always an *output* of the stop distance and the risk budget:

```
lots = f(equity, risk_pct, stop_distance, broker_spec)
```

Because size is derived this way, martingale, post-loss multipliers, averaging down
and grid recovery are not merely disabled — they are **unrepresentable**. There is
no code path that can increase size because a position is losing.

## 2. Prohibited outright

```
fixed lot size as a production default
martingale
lot multiplier after a loss
averaging down
grid recovery
increasing size because a trade is losing
widening a stop to avoid a loss
increasing risk to satisfy a broker minimum lot
```

`tests/parity/test_implementation_correspondence.py` fails the build if any of
these terms appears in the MQL4 sources outside a prohibition comment.

## 3. Position sizing

```
risk_money      = equity * risk_pct / 100
stop_distance   = |entry - stop|                    (> 0 required)
ticks           = stop_distance / tick_size          (tick_size is a PRICE)
risk_per_lot    = ticks * tick_value
lots            = floor(risk_money / risk_per_lot / lot_step) * lot_step
```

Two rules carry the whole safety argument:

1. **Always round DOWN** to the broker lot step. Rounding up silently exceeds the
   mandate. A relative epsilon (1e-9) compensates float representation only — a
   true 1.0 arriving as 0.999999999 must not lose a whole lot step — and realized
   risk is re-checked against the budget afterwards.
2. **Never round up to the minimum lot.** If the broker's minimum lot implies more
   risk than `risk_pct` permits, the system **does not trade**. This is absolute.

> **Tick-size note.** `MODE_TICKSIZE` is the minimal **price** increment (0.01 on a
> 2-digit XAUUSD), not a count of points. Multiplying it by `Point` — as the source
> audit's sample code does — understates every position 100× on a 2-digit gold
> feed. See `RESEARCH_SOURCES.md`.

Sizing fails closed (returns zero lots with a reason code) on: an invalid broker
spec, a non-finite input, non-positive equity, a zero-width stop, or any
computation that would exceed the budget.

## 4. Account-level controls

| Control | V1 default | Effect when breached |
|---|---|---|
| Risk per trade | **0.35%** of equity | — |
| Max concurrent positions | **1** | Second entry refused |
| Max aggregate strategy risk | 0.75% | Second entry refused |
| Daily loss stop | **−1.5%** of day-start equity | New entries blocked for the rest of the day |
| Weekly loss stop | **−3.0%** of week-start equity | New entries blocked for the rest of the week |
| Soft equity drawdown | **−5.0%** from peak | Risk per trade **halved** (0.35% → 0.175%) |
| Hard equity drawdown | **−9.0%** from peak | **Latched halt**; manual operator reset required |

Day and week boundaries are evaluated in **broker server time**, with the reference
equity snapshotted at the first observation of the new period.

### Semantics that matter in an incident

- **A tripped limit blocks new entries. It does not liquidate.** Open positions
  continue to be managed under the exit rules; their stops are never widened or
  removed because a limit tripped. Forced liquidation converts a drawdown into a
  realized loss at the worst possible moment, and is not part of this policy.
- **The hard drawdown kill latches.** Recovering equity does not silently re-enable
  trading. `reset_hard_kill(operator)` requires a named operator and refuses an
  empty identity.
- **Block reasons are severity-ordered** so telemetry names the most serious active
  block: `SAFE_MODE` → `HARD_DRAWDOWN_KILL` → `WEEKLY_LOSS_STOP` →
  `DAILY_LOSS_STOP`.
- **Soft drawdown de-risks rather than stopping.** Halving risk keeps the system
  participating while materially reducing the cost of being wrong about the
  drawdown's cause.

## 5. Safe mode

Entered when state reconstruction is inconsistent — most importantly when more than
one strategy position is found on restart, which §7.2 of the spec forbids. In safe
mode the EA manages existing positions, opens nothing new, and raises an alert.

Safe mode outranks every other block reason.

## 6. Margin

Leverage determines **margin consumption**, never risk. The 0.35% per-trade budget
holds regardless of how much leverage the venue permits.

Before every order the EA validates free margin via `AccountFreeMarginCheck()` in
addition to the sizing calculation. A system designed around maximum available
leverage is designed around the broker's risk appetite rather than its own.

Under ESMA rules gold CFDs for retail clients carry a 20:1 leverage cap, 50%
margin-close-out and negative balance protection. Those are venue constraints, not
this policy — the mandate here is stricter and independent of them.

## 7. Fail-closed

When uncertain, the answer is **NO TRADE**:

```
invalid or missing broker specification   non-finite indicator values
ATR <= 0                                  insufficient history
unresolvable or inconsistent time         corrupted/missing news file (when required)
uncertain state reconstruction            spread beyond threshold
stale quotes                              margin validation failure
any sizing failure
```

A trading system must fail closed, never fail into the market.

## 8. Changing this policy

Any change to a value in §4 requires:

1. an explicit statement of the risk being accepted;
2. an update to `RiskPolicyParams`, `RpbRisk` defaults and this document **in the
   same change set**;
3. review by the `risk` specialist per `docs/ai-engineering/ROUTING_RULES.md`.

Changing a risk value because a backtest performed better with it is a violation of
the mandate, not a tuning step.
