# XAUUSD Regime-Filtered Pullback → Breakout — Frozen Strategy Contract

- Strategy id: `XAU_RPB`
- Specification version: **`XAU_RPB_V1.0.0`**
- Status: **FROZEN for V1 research.** Any change to a `STRUCTURAL` rule requires a version
  bump and invalidates every backtest produced under the previous version.
- Canonical implementation: `research/strategies/xau_rpb/` (Python)
- Mirror implementation: `mt4/Experts/XauRpbEA.mq4` (MQL4), verified by `tests/parity/`
- Architectural authority: `docs/ADR/0027-standalone-xauusd-rpb-expert-advisor.md`

> This document is written so that two independent developers implementing it against the
> same OHLC series produce **the same trading signals**. Where a rule could be read two
> ways, the tie-break is stated explicitly. Vague language ("strong trend", "good pullback")
> is deliberately absent.

---

## 1. Scope and instrument

One instrument: gold against USD, resolved by alias (§10). One strategy family. The
following are **out of scope and prohibited** in this specification: grid, martingale,
averaging down, recovery sizing, pivot reversal, unrelated scalpers, and any machine-learned
directional prediction.

## 2. Timeframe architecture

| Role | Timeframe | Bar used |
|---|---|---|
| Market regime / context | H1 | closed bar, `shift = 1` |
| Setup + trigger | M15 | closed bar, `shift = 1` |
| Position management / execution | tick stream | live |

**Closed-bar rule (STRUCTURAL, non-negotiable).** Every quantity that participates in a
*confirmed* signal is computed from a bar that has already closed. `shift = 0` is never read
for signal purposes. This eliminates repainting and makes backtest and live agree.

**Bar-close ordering.** When an H1 close and an M15 close coincide (every 4th M15 bar), the
**H1 regime update is applied first**, then the M15 setup logic runs against the updated
regime. This ordering is normative.

## 3. Notation

For a series `x`, `x[i]` is the value `i` closed bars back; `x[1]` is the most recently
closed bar. `H1.*` and `M15.*` denote the timeframe. All indicator definitions below are
exact; no library defaults are assumed.

### 3.1 Indicator definitions (normative)

**EMA** — standard exponential smoothing with `alpha = 2 / (n + 1)`, seeded with the simple
mean of the first `n` values:

```
EMA[n](t0) = mean(close[t0-n+1 .. t0])
EMA[n](t)  = close(t)*alpha + EMA[n](t-1)*(1-alpha)
```

**True Range**

```
TR(t) = max( high(t) - low(t),
             abs(high(t) - close(t-1)),
             abs(low(t)  - close(t-1)) )
```

**ATR** — Wilder smoothing (RMA), seeded with the simple mean of the first `n` true ranges:

```
ATR[n](t0) = mean(TR[t0-n+1 .. t0])
ATR[n](t)  = (ATR[n](t-1)*(n-1) + TR(t)) / n
```

**ADX** — Wilder, period `n`:

```
up   = high(t) - high(t-1)
down = low(t-1) - low(t)
+DM  = up   if (up > down   and up > 0)   else 0
-DM  = down if (down > up   and down > 0) else 0
```

`+DM`, `-DM` and `TR` are Wilder-smoothed (the same RMA as ATR) over `n`. Then

```
+DI = 100 * RMA(+DM) / RMA(TR)
-DI = 100 * RMA(-DM) / RMA(TR)
DX  = 100 * abs(+DI - -DI) / (+DI + -DI)      (DX = 0 when +DI + -DI = 0)
ADX = RMA(DX) over n
```

**Efficiency Ratio** over window `n`:

```
ER(t) = abs(close(t) - close(t-n)) / sum_{i=t-n+1..t} abs(close(i) - close(i-1))
```

`ER = 0` when the denominator is 0.

**ATR percentile** — the fraction of the trailing `atr_pct_window` H1 ATR values strictly
less than the current ATR:

```
ATRpct(t) = count{ i in [t-W+1, t] : ATR(i) < ATR(t) } / W
```

Ties count as "not less than", which makes the statistic monotone and reproducible.

## 4. Regime engine (H1)

Computed once per closed H1 bar from `shift = 1`.

```
ema_fast          = H1.EMA[ema_fast_period](1)
ema_slow          = H1.EMA[ema_slow_period](1)
atr_h1            = H1.ATR[atr_period_h1](1)
adx               = H1.ADX[adx_period](1)
er                = H1.ER[er_window](1)
atr_pct           = H1.ATRpct(1)

normalized_spread = (ema_fast - ema_slow) / atr_h1
normalized_slope  = ( H1.EMA[ema_fast_period](1)
                    - H1.EMA[ema_fast_period](1 + slope_lookback) )
                    / (slope_lookback * atr_h1)
```

### 4.1 Classification (evaluated strictly in this order — first match wins)

```
1. if history insufficient for any input, or atr_h1 <= 0, or any input non-finite:
       REGIME_INVALID
2. if atr_pct >= atr_pct_high:
       REGIME_HIGH_VOLATILITY                      (risk-off; no new trades)
3. if adx >= adx_trend_min
   and normalized_spread >=  spread_trend_min
   and normalized_slope  >=  slope_trend_min
   and er                >=  er_trend_min:
       REGIME_TREND_UP
4. if adx >= adx_trend_min
   and normalized_spread <= -spread_trend_min
   and normalized_slope  <= -slope_trend_min
   and er                >=  er_trend_min:
       REGIME_TREND_DOWN
5. if adx < adx_range_max:
       REGIME_RANGE
6. otherwise:
       REGIME_INVALID
```

The ordering is normative: **HIGH_VOLATILITY dominates trend** (a violent trend is still
risk-off), and `REGIME_INVALID` is the catch-all for the transition band between
`adx_range_max` and `adx_trend_min`.

### 4.2 Trading permission

New positions may be opened **only** in `REGIME_TREND_UP` (long only) and
`REGIME_TREND_DOWN` (short only). `RANGE`, `HIGH_VOLATILITY` and `INVALID` are all
**NO NEW TRADE**. This is a hard gate, not a score component.

## 5. Setup state machine (M15)

One state machine instance. States:

```
SCANNING -> ARMED -> PULLBACK_ACTIVE -> BREAKOUT_WINDOW -> SIGNAL_READY
         -> ORDER_SUBMITTED -> IN_POSITION -> SCANNING
```

Every transition below is total: for each state the conditions are evaluated in the listed
order and the first match fires. If none matches, the state is retained.

Let `dir = +1` in `TREND_UP`, `dir = -1` in `TREND_DOWN`. For a closed bar `i`:

```
counter_trend(i)  ==  dir * (close(i) - open(i)) < 0     (a bar closing against dir)
atr_m15           =   M15.ATR[atr_period_m15](1)
```

### 5.1 SCANNING

```
if regime in {TREND_UP, TREND_DOWN}:  -> ARMED   (record dir; reset setup fields)
else:                                    stay
```

### 5.2 ARMED — locate the impulse leg

When a counter-trend bar appears, the impulse leg is measured over the
`impulse_lookback` closed bars **ending at bar 2** — that is, the bars that preceded the
pullback. Bar 1 is excluded deliberately: folding the pullback bar's own low into
`swing_origin` would make the structural-invalidation test in §5.3 unfalsifiable.

```
swing_extreme = max(high[2 .. impulse_lookback+1])   if dir = +1
                min(low [2 .. impulse_lookback+1])   if dir = -1
swing_origin  = min(low [2 .. impulse_lookback+1])   if dir = +1
                max(high[2 .. impulse_lookback+1])   if dir = -1
```

```
1. if regime not in {TREND_UP, TREND_DOWN} or dir changed:  -> SCANNING
2. if counter_trend(1):
       if insufficient history for the impulse window:      stay
       pullback_bars      = 1
       pullback_extreme   = low(1)  if dir=+1 else high(1)
       breakout_reference = max(high(1), high(2))  if dir=+1
                            min(low(1),  low(2))   if dir=-1
       if depth > max_pullback_depth_atr:                   -> SCANNING
       if dir=+1 and pullback_extreme < swing_origin:       -> SCANNING
       if dir=-1 and pullback_extreme > swing_origin:       -> SCANNING
       -> PULLBACK_ACTIVE
3. else: stay
```

`breakout_reference` deliberately includes bar 2 (the last impulse bar) so the level to be
broken is the structure high/low the pullback retraced from, not merely the pullback bar's
own extreme. The depth and structure tests are applied at the pullback's first bar as well
as on every later one: a "pullback" that immediately breaks the impulse origin is not a
pullback.

### 5.3 PULLBACK_ACTIVE

On each closed M15 bar:

```
1. if regime invalidated or dir changed:                     -> SCANNING
2. if counter_trend(1):
       pullback_bars     += 1
       pullback_extreme   = min(pullback_extreme, low(1))   if dir=+1 else max(.., high(1))
       breakout_reference = max(breakout_reference, high(1)) if dir=+1 else min(.., low(1))
       if pullback_bars > max_pullback_bars:                 -> SCANNING  (too long)
       if depth > max_pullback_depth_atr:                    -> SCANNING  (too deep)
       if dir=+1 and pullback_extreme < swing_origin:        -> SCANNING  (structure lost)
       if dir=-1 and pullback_extreme > swing_origin:        -> SCANNING
       stay
3. else (first non-counter-trend bar - the pullback is over):
       if pullback_bars < min_pullback_bars:                 -> SCANNING
       if depth < min_pullback_depth_atr:                    -> SCANNING  (too shallow)
       if depth > max_pullback_depth_atr:                    -> SCANNING
       window_bars_left   = breakout_window_bars
       -> BREAKOUT_WINDOW
       then evaluate breakout_confirmed(1) on THIS bar (see below)
```

`breakout_reference` is **frozen at the pullback structure** and is NOT extended with the
recovery bar's own high/low. Extending it would make the recovery bar — the classic
pullback-breakout entry bar — structurally incapable of triggering, and would bias every
entry one bar late. The recovery bar is therefore the first bar evaluated by the §5.4
trigger; if it does not confirm, the window covers the following `breakout_window_bars`.

where the ATR-normalized retracement depth is

```
depth = abs(swing_extreme - pullback_extreme) / atr_m15        (atr_m15 > 0 required)
```

### 5.4 BREAKOUT_WINDOW

On each closed M15 bar:

```
1. if regime invalidated or dir changed:                     -> SCANNING
2. if breakout_confirmed(1):                                 -> SIGNAL_READY
3. window_bars_left -= 1
   if window_bars_left <= 0:                                 -> SCANNING  (timeout)
   if setup_age_bars >= max_setup_bars:                      -> SCANNING  (lifetime cap)
   stay
```

with the **breakout trigger (STRUCTURAL)**:

```
LONG :  close(1) >  breakout_reference + breakout_buffer_atr * atr_m15
SHORT:  close(1) <  breakout_reference - breakout_buffer_atr * atr_m15
```

Strict inequality. The trigger uses the **close of a closed M15 bar**. Intrabar highs/lows
never confirm a breakout in V1; an intrabar variant may exist only as a separately named and
separately tested execution variant, never as the production definition.

### 5.5 SIGNAL_READY -> ORDER_SUBMITTED -> IN_POSITION

`SIGNAL_READY` evaluates the score (§6) and the execution guards (§9). Outcome:

```
score < entry_score_threshold   -> SCANNING   (logged, SCORE_BELOW_THRESHOLD)
any execution guard rejects     -> SCANNING   (logged with the guard's reason code)
sizing yields 0 lots            -> SCANNING   (logged, RISK_SIZE_ZERO)
otherwise                       -> ORDER_SUBMITTED
```

`ORDER_SUBMITTED -> IN_POSITION` on a confirmed fill; `ORDER_SUBMITTED -> SCANNING` on a
terminal broker rejection. `IN_POSITION -> SCANNING` when the position closes for any reason
in §8. Exactly one position may exist (§7.2), so no second setup is armed while
`IN_POSITION`.

## 6. Signal score

Seven independent, interpretable factors; maximum **9**.

| # | Factor | Points |
|---|---|---|
| 1 | H1 regime is `TREND_UP`/`TREND_DOWN` matching `dir` | +2 |
| 2 | `abs(normalized_slope) >= score_slope_min` | +1 |
| 3 | `min_pullback_depth_atr <= depth <= max_pullback_depth_atr` | +1 |
| 4 | Breakout confirmed on a closed M15 bar (§5.4) | +2 |
| 5 | `atr_pct_floor <= atr_pct < atr_pct_high` | +1 |
| 6 | Entry bar falls inside a permitted liquid session (§11) | +1 |
| 7 | `spread <= spread_atr_max * atr_m15` **and** `spread <= spread_abs_max_points` | +1 |

Entry requires `score >= entry_score_threshold`. Factors 1 and 4 are also hard gates
(§4.2, §5.4) — the score can never substitute for them; it can only make an otherwise valid
setup ineligible. The research objective for `entry_score_threshold` is a **stable plateau**
across {6, 7, 8}, not the value maximizing historical profit.

## 7. Risk

Risk is computed **independently of signal generation**. A signal never influences the risk
percentage, and risk never influences direction.

### 7.1 Position sizing (broker-aware)

```
risk_money      = AccountEquity * risk_pct / 100
stop_distance   = abs(entry_price - stop_price)             (price units, > 0 required)
ticks           = stop_distance / tick_size                 (tick_size is a PRICE)
risk_per_lot    = ticks * tick_value
lots_raw        = risk_money / risk_per_lot
lots            = floor(lots_raw / lot_step) * lot_step      (ALWAYS round DOWN)
```

Then, in order:

```
if any of {point, tick_size, tick_value, lot_step, min_lot} <= 0 or non-finite: NO TRADE
if stop_distance <= 0:                                                          NO TRADE
if lots > max_lot:  lots = floor(max_lot / lot_step) * lot_step
if lots < min_lot:  NO TRADE                                    <- never round up
```

> **Correction to the source audit.** The audit's sample code computes
> `tickSizePrice = tickSizePoints * Point`, treating `MODE_TICKSIZE` as a count of
> points. It is not: MT4's `MODE_TICKSIZE` is the minimal **price** increment
> (0.01 on a 2-digit XAUUSD). Multiplying it by `Point` understates every position
> by a factor of `1/Point` — 100x on a 2-digit gold feed. This specification uses
> `tick_size` directly, and `tests/unit/strategy/test_sizing.py` pins the economics
> (0.5 lots of a 100 oz contract risking exactly $500 over a $10 stop).

**The minimum-lot rule is normative and absolute:** if the broker's minimum lot implies more
risk than `risk_pct` permits, the system does **not** trade. Risk is never increased to
satisfy a broker minimum.

### 7.2 Account-level controls

| Control | V1 default | Kind |
|---|---|---|
| Risk per trade | 0.35 % of equity | RISK POLICY |
| Max concurrent `XAU_RPB` positions | 1 | RISK POLICY |
| Max aggregate strategy risk | 0.75 % | RISK POLICY |
| Daily loss stop | −1.5 % of day-start equity | RISK POLICY |
| Weekly loss stop | −3.0 % of week-start equity | RISK POLICY |
| Soft equity drawdown | −5.0 % from peak equity -> risk halved | RISK POLICY |
| Hard equity drawdown | −9.0 % from peak equity -> **halt, manual reset** | RISK POLICY |

Kill-switch semantics: a breached daily/weekly stop blocks **new entries** for the remainder
of that period; open positions continue to be managed by §8 (stops are never widened or
removed). The hard drawdown kill blocks new entries until an operator resets it; it does not
liquidate, because forced liquidation converts a drawdown into a realized loss at the worst
possible moment. Day and week boundaries are evaluated in **broker server time**, with the
reference equity snapshotted at the first tick of the new period.

**Prohibited by specification:** fixed lot size as a production default, martingale, lot
multipliers after losses, averaging down, grid recovery, and any size increase because a
position is losing.

## 8. Exits

Initial stop, at entry:

```
LONG :  stop = entry - sl_atr_mult * atr_m15
SHORT:  stop = entry + sl_atr_mult * atr_m15
```

`atr_m15` is the value at the **signal bar**, frozen for the life of the trade (a stop that
re-computes from a moving ATR is not reproducible). `R` is the initial `abs(entry - stop)`
distance in price units.

Exit variants (research families):

- **A — fixed R target:** take profit at `tp_r_multiple * R`, no trailing.
- **B — ATR trailing:** no fixed target; once `trail_activate_r` is reached the stop trails
  `trail_atr_mult * atr_m15` behind the extreme reached since entry, and only ever moves in
  the favorable direction.
- **C — hybrid (V1 default):** ATR trailing as in B, plus optional break-even at
  `be_trigger_r`, and no fixed target — so a positive tail is not truncated.

Additional terminating conditions, evaluated on each closed M15 bar:

- **Time exit** — position age `>= max_bars_in_trade` M15 bars.
- **Regime invalidation exit** — H1 regime becomes the *opposite* trend (`TREND_DOWN` while
  long, `TREND_UP` while short). A move to `RANGE`, `HIGH_VOLATILITY` or `INVALID` does
  **not** force an exit in V1; it only blocks new entries.
- **Session exit** — optional (`session_exit_enabled`), closes at the end of the window.

A stop is never widened, and risk is never increased, to keep a losing position alive.

### 8.1 Exit reason codes (machine-readable, mandatory)

```
STOP_LOSS · TARGET · ATR_TRAIL · REGIME_INVALIDATION · TIME_EXIT
SESSION_EXIT · RISK_KILL · MANUAL · BROKER_ERROR_RECOVERY
```

Every closed trade carries exactly one. Reasons are recorded by the component that caused
the exit — never inferred afterwards from the price path.

## 9. Execution guards

**Signal validity and order executability are separate concerns.** A valid signal that fails
any guard is rejected and logged; it is never "fixed" by relaxing the signal.

Evaluated before every order submission, all must pass:

```
terminal trading allowed          symbol trading allowed        broker spec valid (§7.1)
spread within limits (§6 f.7)     quote freshness within tolerance
stop respects MODE_STOPLEVEL      price respects MODE_FREEZELEVEL
lot valid vs min/step/max         free margin sufficient (AccountFreeMarginCheck > 0)
no existing strategy position     no duplicate signal for this bar
daily / weekly / hard-DD kill switches all clear
news blackout not active (§12)    session permitted (§11)
sufficient indicator history      atr_m15 > 0 and finite
```

Retry policy: bounded (`max_retries`, default 3), error-aware (only transient MT4 errors —
requote, off-quotes, trade context busy, price changed — are retried; invalid stops, invalid
volume and insufficient margin are terminal), and every attempt logged. **No infinite retry
loops. Stops are never widened and risk is never increased to obtain broker acceptance.**

## 10. Broker abstraction

Nothing about the instrument may be hardcoded. The EA must **not** assume 2 digits,
`Point = 0.01`, contract size 100, constant tick value, min lot 0.01, constant stop level,
server timezone UTC+2, or the literal symbol name `XAUUSD`.

Queried dynamically: `MODE_POINT`, `MODE_DIGITS`, `MODE_SPREAD`, `MODE_TICKVALUE`,
`MODE_TICKSIZE`, `MODE_LOTSIZE`, `MODE_MINLOT`, `MODE_LOTSTEP`, `MODE_MAXLOT`,
`MODE_STOPLEVEL`, `MODE_FREEZELEVEL`, `MODE_SWAPLONG`, `MODE_SWAPSHORT`,
`MODE_PROFITCALCMODE`, `MODE_MARGINCALCMODE`.

Symbol resolution walks a configurable alias list (default: `XAUUSD`, `GOLD`, `XAUUSD.a`,
`XAUUSDm`, `XAUUSD.m`, `XAUUSD_i`, `XAUUSDpro`, `GOLD.a`) and selects the first alias that
exists and returns a valid specification. If none resolves: **fail closed, do not trade.**

## 11. Sessions and time

Broker server time is **not** assumed to be any particular offset. The normalization chain is
explicit and logged:

```
broker server timestamp -> broker UTC offset -> UTC -> London / New York local -> flags
```

The broker offset is determined once per session-day and recorded in telemetry and in every
backtest config snapshot, so a run is reproducible.

| Session | Local window | Zone |
|---|---|---|
| London | 08:00 – 16:30 | `Europe/London` |
| New York | 08:00 – 17:00 | `America/New_York` |
| Overlap | intersection of the two | — |
| Asian | 09:00 – 17:00 | `Asia/Tokyo` |
| Rollover | 21:00 – 23:00 UTC | — (structurally wide spreads) |

V1 default permitted window: **London ∪ New York, excluding rollover.** Per-session
performance is reported separately rather than assumed.

## 12. News filter

News never predicts direction in V1. High-impact events act **only** as a risk filter,
blocking new entries inside

```
[ event_time - news_block_before_min , event_time + news_block_after_min ]
```

Default 30 minutes before, 15 minutes after. Supported classes: CPI, NFP, FOMC, Fed Chair
speeches, and other USD high-impact events.

The calendar is a **frozen, versioned CSV** (`data/fixtures/xau_rpb/news_*.csv`), never a
live API: `WebRequest()` does not execute inside the MT4 Strategy Tester, and a backtest
whose inputs can change is not reproducible. A missing, unreadable or malformed news file
**fails closed** (no new entries) when `news_required = true`.

CSV schema (UTC, ISO-8601, header mandatory):

```
event_time_utc,currency,impact,event_name
2024-01-11T13:30:00Z,USD,HIGH,CPI m/m
```

## 13. State recovery

MT4 restarts, charts reload, EAs get reattached, connections drop. On every initialization
the EA must:

1. enumerate open orders and history;
2. identify its own by `MagicNumber` **and** order-comment prefix (`XAU_RPB_V1`);
3. rebuild execution state (`IN_POSITION` if one is found, else `SCANNING`);
4. never create a duplicate entry for a setup already acted upon;
5. resume management of the recovered position under §8.

If more than one strategy position is found — a state §7.2 forbids — the EA enters
**SAFE MODE**: it manages existing positions, opens nothing new, and raises an alert.
Uncertain state reconstruction always resolves to "do not trade" (§15).

## 14. Parameters

Every parameter is classified. **Only `RESEARCH` parameters may be optimized.**

### STRUCTURAL — define the strategy; changing one is a new spec version

| Parameter | V1 | Meaning |
|---|---|---|
| `use_closed_bars` | `true` | Signals from closed bars only |
| `regime_timeframe` | H1 | Regime timeframe |
| `setup_timeframe` | M15 | Setup/trigger timeframe |
| `breakout_on_close` | `true` | Close-confirmed breakout (not intrabar) |
| `max_concurrent_positions` | 1 | One position at a time |

### RESEARCH — seeds with defensible neighbourhoods; subject to sensitivity analysis

| Parameter | Seed | Research region |
|---|---|---|
| `ema_fast_period` | 50 | 34 – 62 |
| `ema_slow_period` | 200 | 150 – 250 |
| `adx_period` | 14 | 10 – 20 |
| `adx_trend_min` | 20.0 | 18 – 25 |
| `adx_range_max` | 18.0 | 14 – 20 |
| `spread_trend_min` | 0.25 | 0.15 – 0.40 |
| `slope_trend_min` | 0.03 | 0.01 – 0.06 |
| `slope_lookback` | 3 | 2 – 6 |
| `er_window` | 20 | 10 – 30 |
| `er_trend_min` | 0.30 | 0.20 – 0.45 |
| `atr_period_h1` | 14 | 10 – 20 |
| `atr_period_m15` | 14 | 10 – 20 |
| `atr_pct_window` | 500 | 250 – 750 |
| `atr_pct_high` | 0.95 | 0.90 – 0.98 |
| `atr_pct_floor` | 0.10 | 0.05 – 0.25 |
| `impulse_lookback` | 6 | 4 – 10 |
| `min_pullback_bars` | 1 | 1 – 2 |
| `max_pullback_bars` | 4 | 3 – 6 |
| `min_pullback_depth_atr` | 0.30 | 0.20 – 0.50 |
| `max_pullback_depth_atr` | 2.00 | 1.50 – 3.00 |
| `breakout_window_bars` | 3 | 2 – 5 |
| `breakout_buffer_atr` | 0.10 | 0.05 – 0.20 |
| `max_setup_bars` | 12 | 8 – 20 |
| `entry_score_threshold` | 7 | 6 – 8 |
| `score_slope_min` | 0.03 | 0.01 – 0.06 |
| `sl_atr_mult` | 2.00 | 1.50 – 2.50 |
| `tp_r_multiple` | 0 (none) | 0 / 2 / 3 / 4 |
| `trail_atr_mult` | 2.00 | 1.50 – 3.00 |
| `trail_activate_r` | 1.00 | 0.5 – 1.5 |
| `be_trigger_r` | 0 (off) | 0 / 1.0 / 1.5 |
| `max_bars_in_trade` | 48 | 24 – 96 |

### RISK POLICY — mandate values, **not** alpha variables; never "optimized"

`risk_pct` 0.35 · `max_aggregate_risk_pct` 0.75 · `daily_loss_stop_pct` 1.5 ·
`weekly_loss_stop_pct` 3.0 · `soft_dd_pct` 5.0 · `hard_dd_pct` 9.0 ·
`max_concurrent_positions` 1

### EXECUTION — venue-dependent; tuned to the venue, never to the P&L

`spread_atr_max` is calibrated from XAUUSD microstructure, not from results:
typical gold spread / M15-ATR sits near 0.05-0.12, so 0.12 admits normal
conditions and rejects roughly 2x-normal blowouts. A tighter 0.06 was measured to
reject nearly every otherwise-valid setup.

`spread_atr_max` 0.12 · `spread_abs_max_points` 60 · `max_slippage_points` 20 ·
`max_retries` 3 · `retry_delay_ms` 250 · `quote_max_age_sec` 5 ·
`magic_number` 20260831 · `symbol_aliases` (§10)

### OPERATIONAL — no effect on signals

`mode` (`SHADOW` | `LIVE`) · `log_level` · `telemetry_path` · `news_csv_path` ·
`news_required` · `session_exit_enabled` · `broker_utc_offset_hours` (`AUTO` by default)

## 15. Fail-closed principle

When the system is uncertain, the answer is **NO TRADE**. Explicitly: invalid or missing
broker specification, non-finite indicator values, `ATR <= 0`, insufficient history,
inconsistent or unresolvable time, corrupted or missing news file (when required), uncertain
state reconstruction, spread beyond threshold, stale quotes, margin validation failure, or
any sizing failure.

A trading system must fail closed, never fail into the market.

## 16. Versioning

`XAU_RPB_V1.0.0` is stamped into EA metadata, every telemetry record, every order comment,
every research config snapshot and every backtest report. **A backtest report without a
strategy version and config hash is not reproducible and is not evidence.**
