# XAU_RPB — Broker Compatibility and XAUUSD-Specific Audit

Mandate §64 asks for a dedicated audit of the assumptions that routinely break gold
EAs. Each row below is an assumption this implementation **does not** make, with
the mechanism that prevents it.

---

## 1. The XAUUSD failure list

| Common assumption | Why it breaks | What this implementation does |
|---|---|---|
| XAUUSD always has 2 digits | Brokers ship 2- and 3-digit gold | `MODE_DIGITS` read at init; `NormalizeDouble` uses it everywhere |
| `Point == 0.01` | Follows digits | `MODE_POINT` read at init |
| Contract size == 100 oz | Varies (10 oz mini accounts exist) | `MODE_LOTSIZE` read; never used as a sizing constant |
| Tick value is constant | Varies by account currency and venue | `MODE_TICKVALUE` read at init |
| `MODE_TICKSIZE` is a count of points | **It is a PRICE.** Treating it as points understates size 100× on a 2-digit feed | Used directly as a price; pinned by `test_sizing.py` |
| Pip == point | Gold has no universal "pip" | The word "pip" appears nowhere in the logic; everything is points or price |
| Min lot == 0.01 | Some venues require 0.1 | `MODE_MINLOT` read; below it the system **does not trade** rather than rounding up |
| Lot step == 0.01 | Varies | `MODE_LOTSTEP` read; sizing always floors to it |
| Stop level is constant | Widens around news and rollover | `MODE_STOPLEVEL` re-read per order; violations rejected, never "fixed" by widening |
| Freeze level is ignorable | Blocks modify/close near market | `MODE_FREEZELEVEL` checked before submission |
| Symbol is literally `XAUUSD` | `GOLD`, `XAUUSD.a`, `XAUUSDm`, `XAUUSDpro`, … | Configurable alias list; first alias returning a **valid spec** wins; none → no trade |
| Server timezone is UTC+2 | Varies by broker and season | Explicit offset input; auto-detection is logged, and is deliberately overridden inside the Strategy Tester |
| Spreads are stable | Rollover and news spikes are routine | Adaptive filter: relative (spread/ATR) **and** absolute ceiling; rollover window excluded by default |
| Swap is negligible | Gold swaps can be material | `MODE_SWAPLONG` / `MODE_SWAPSHORT` read and charged per night held |
| Slippage is zero | It is not | Explicit slippage tolerance; stress scenarios re-execute the strategy at +0/+1/+2/+3 points |
| Gaps do not happen | Weekend and news gaps do | Stops are broker-side; the backtest treats a bar containing both stop and target as a **stop first** |
| Profit/margin calc modes are uniform | They are not | `MODE_PROFITCALCMODE` / `MODE_MARGINCALCMODE` captured for the record |

## 2. Symbol resolution

Default alias list (configurable via `InpSymbolAliases`):

```
XAUUSD, GOLD, XAUUSD.a, XAUUSDm, XAUUSD.m, XAUUSD_i, XAUUSDpro, GOLD.a
```

Resolution walks the list in order and selects the first alias that both exists
(`MODE_POINT > 0`) **and** returns a specification passing every validity check.
The resolved symbol and its full specification are printed at init, so the log
always records which instrument was actually traded.

If nothing resolves, `OnInit` returns `INIT_FAILED`. There is no fallback symbol.

## 3. Specification validity gate

A specification is usable only when **all** hold:

```
point > 0        tick_value > 0     tick_size > 0
min_lot > 0      lot_step > 0       max_lot >= min_lot
```

Any failure means no trade — not a default value. Substituting a plausible default
for a missing broker value is the mechanism by which position sizing silently
becomes wrong.

## 4. Timezone and DST

MT4 has no timezone database, so the EA computes DST from the actual rules:

- **Europe/London**: last Sunday of March 01:00 UTC → last Sunday of October 01:00 UTC
- **America/New_York**: second Sunday of March → first Sunday of November
- **Asia/Tokyo**: no DST

The Python reference uses `zoneinfo` (with `tzdata`), and the two are compared by
the parity fixtures. Session boundaries are asserted directly in
`tests/unit/strategy/test_sessions_and_news.py`, including the summer/winter shift
that silently moves a naively-built London rule by an hour.

**Strategy Tester caveat.** MetaQuotes documents that `TimeLocal()` and `TimeGMT()`
track the simulated server time inside the tester, so auto-detection there would
return a meaningless offset. The EA detects `IsTesting()` and falls back to the
explicit `InpBrokerUtcOffsetHrs`, printing that it has done so. A backtest whose
session rule differs from production is worse than no backtest.

## 5. Recommended venue characteristics

Not requirements — the EA runs anywhere — but the conditions under which this
strategy family is plausible:

| Characteristic | Preference | Why |
|---|---|---|
| Typical XAUUSD spread | ≤ 25 points (2-digit) | The relative filter rejects wide spreads; a structurally wide venue simply will not trade |
| Stop level | Low / zero | Large stop levels can reject valid ATR stops |
| Execution | Market, no dealing-desk requote loops | Retries are bounded at 3 and never widen the stop |
| Server time | Stable, documented offset | Session reproducibility |
| History depth | 5+ years M15 | Below the mandate minimum, conclusions are weakly supported |

## 6. Per-broker record

For multi-broker validation (§38), capture per broker **and per period**:

```
Digits · Point · TickSize · TickValue · LotSize · MinLot · LotStep · MaxLot
StopLevel · FreezeLevel · Spread · SwapLong · SwapShort
ProfitCalcMode · MarginCalcMode · server UTC offset
```

The EA prints most of this at init. Store it beside each dataset so a later
divergence between feeds can be attributed to specification differences rather
than to alpha.

## 7. Verified against a live terminal (2026-08-31)

Measured on this machine, not assumed:

| Item | Result |
|---|---|
| Terminal | MetaTrader 4 IC Markets Global (`C:/Program Files (x86)/MetaTrader 4 IC Markets Global`) |
| Data folder | `%APPDATA%/MetaQuotes/Terminal/5D49F47D...` |
| **EA compilation** | **`0 errors, 0 warnings`** (`metaeditor.exe /compile`) |
| Parity harness compilation | `0 errors, 0 warnings` |
| Symbol | resolves as literal `XAUUSD`, **2 digits** |
| Account seen by the existing bridge | demo 44961955, `is_demo=True` |
| M15 history, this terminal | 27,636 bars, 2025-04-30 → 2026-06-30 (1.17 y) |
| M15 history, second terminal (`1DAFD9A7…`) | **448,172 bars, 2004-06-11 → 2024-01-09 (19.58 y)** |
| Data quality (19.6 y) | CLEAN — 0 duplicates, 0 out-of-order, 0 impossible OHLC |
| **Spread in `.hst`** | **always 0 — MT4 does not retain per-bar spread.** Must be modelled and labelled |

### Server UTC offset — measured, not assumed

The M15 bar histogram shows **zero bars at server hour 00:00** all year round, and the
week opens Monday 01:00 server. Gold's daily break is 22:00-23:00 UTC in winter and
21:00-22:00 UTC in summer. A server whose break stays fixed in its own clock while the
UTC break moves must itself be moving:

```
IC Markets server = UTC+2 (winter)  /  UTC+3 (summer), following US DST
```

**This invalidated a fixed-offset assumption.** `SessionResolver` originally took a
constant offset, which would have misplaced every session boundary by one hour for
roughly half of each year. It now accepts a per-timestamp callable, and
`us_dst_broker_offset()` implements the rule above. Verify this per broker: not every
venue follows US DST.

## 8. Known limitations

- ~~Compilation is unverified.~~ **RESOLVED 2026-08-31**: compiles with 0 errors,
  0 warnings against MT4 IC Markets Global (see §7).
- **MQL4-side signal parity is still unverified.** The harness compiles, but MT4
  cannot run a script from the command line, so producing the `.actual` files needs
  one manual step: drag `XauRpbParityHarness` onto a chart once per scenario.
- **Historical spread is modelled, not observed** (the `.hst` carries none), so every
  cost figure depends on that assumption. Stress it before trusting any result.
- The news calendar is capped at 4096 events per file.
- Only one position at a time is supported by design (spec §7.2).
