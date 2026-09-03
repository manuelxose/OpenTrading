# Runbook — XAU_RPB Expert Advisor

Operational guide for `mt4/Experts/XauRpbEA.mq4` (`XAU_RPB_V1.0.0`).

> **Status: RESEARCH / EXPERIMENTAL.** The EA compiles cleanly (0 errors,
> 0 warnings, verified 2026-08-31 on MT4 IC Markets Global), but the strategy has
> **not** passed statistical qualification — measured on 19.6 years of real XAUUSD
> it shows **no edge** (profit factor 0.992 even with zero costs). It ships
> defaulting to `SHADOW` mode, which submits no orders. **Do not connect real
> capital** — see [`RESEARCH_REPORT.md`](../strategy/RESEARCH_REPORT.md).

---

## 1. Installation

```text
<MT4 data folder>/MQL4/Include/xau_rpb/     <- mt4/Include/xau_rpb/*.mqh   (10 files)
<MT4 data folder>/MQL4/Experts/             <- mt4/Experts/XauRpbEA.mq4
<MT4 data folder>/MQL4/Scripts/             <- mt4/tests/XauRpbParityHarness.mq4 (optional)
<MT4 data folder>/MQL4/Files/               <- your frozen news CSV (optional)
```

Find the data folder via **File → Open Data Folder** in the terminal.

## 2. Compilation

Open `XauRpbEA.mq4` in MetaEditor and press F7. It is written for **build 600+**
(classes, `StringSplit`, `StringGetCharacter`, `FileIsLineEnding`).

**Verified 2026-08-31**: compiles with `0 errors, 0 warnings` against MT4
IC Markets Global. The includes compile implicitly via the EA; they are
header-guarded and safe to include in any order.

It can also be compiled headlessly, which is what CI-style checks should use:

```bash
"C:/Program Files (x86)/MetaTrader 4 IC Markets Global/metaeditor.exe" /compile:"<data folder>/MQL4/Experts/XauRpbEA.mq4" /log:"compile.log"
```

The log is UTF-16; look for the final `Result: N errors`. Note `metaeditor.exe`
returns a non-zero exit code even on success, so **parse the log, not the exit
code**.

If MetaEditor reports errors, fix them in `mt4/` in the repository — not only in
the terminal copy — or the two will drift.

## 3. Configuration

Inputs are grouped by the four categories of the specification. **Respect the
grouping**: it is the mechanism that keeps risk policy out of optimization.

| Group | Rule |
|---|---|
| `STRUCTURAL` | Changing one is a new spec version, not a tuning step |
| `RESEARCH` | The only group an optimizer may vary |
| `RISK POLICY` | Mandate values — never optimize |
| `EXECUTION` | Tune to the venue, never to the P&L |
| `OPERATIONAL` | No effect on signals |

### Minimum configuration to start

```
InpMode              = MODE_SHADOW        <- leave here until parity is verified
InpSymbolAliases     = XAUUSD,GOLD,XAUUSD.a,XAUUSDm     (add your broker's name)
InpAutoDetectOffset  = true               (false + explicit offset for backtests)
InpBrokerUtcOffsetHrs= 2.0                (your server's actual offset)
InpTelemetryEnabled  = true
```

Attach to **any** XAUUSD chart. The timeframe of the chart is irrelevant — the EA
reads H1 and M15 explicitly via `iTime`/`iOpen`, so the chart period does not
affect signals.

### News filter (optional)

Place a frozen CSV in `MQL4/Files/` and set `InpNewsCsvFile`:

```csv
event_time_utc,currency,impact,event_name
2024-01-11T13:30:00Z,USD,HIGH,CPI m/m
2024-02-02T13:30:00Z,USD,HIGH,Non-Farm Payrolls
```

Only `HIGH` impact USD rows are loaded. Times are **UTC**. A template lives at
`data/fixtures/xau_rpb/news_template.csv`.

Setting `InpNewsRequired = true` makes the filter fail closed: a missing or
malformed file blocks all new entries rather than trading through an unknown
calendar.

## 4. Startup checks

On a healthy start the Experts log shows:

```
XAU_RPB: resolved symbol 'XAUUSD' digits=2 point=0.01 tickSize=0.01 tickValue=1.0 ...
XAU_RPB: broker UTC offset = 2.00h
XAU_RPB: news calendar '...' loaded, N high-impact USD events
XAU_RPB XAU_RPB_V1.0.0 initialized. mode=SHADOW (no orders will be sent) ...
   | STATUS: RESEARCH/EXPERIMENTAL - not statistically qualified
```

If you instead see `XAU_RPB FAIL-CLOSED: ...`, the EA has refused to start. That is
working as designed — resolve the named cause rather than relaxing the check.

## 5. Telemetry

Written to `MQL4/Files/xau_rpb_telemetry.csv`, append-only across restarts. One row
per decision, with the full feature vector, the score breakdown, the sizing inputs,
and the reject or exit reason.

Use it to answer "why did it not trade?" — the `reject_reason` column names the
guard that blocked each signal:

```
SCORE_BELOW_THRESHOLD   the setup formed but scored below the threshold
SPREAD_TOO_WIDE         relative or absolute spread ceiling exceeded
SESSION_BLOCKED         outside the permitted liquidity window
NEWS_BLACKOUT           inside a high-impact event window
DAILY_LOSS_STOP / WEEKLY_LOSS_STOP / HARD_DRAWDOWN_KILL
RISK_SIZE_ZERO          min lot would exceed the risk budget -> correctly no trade
STOP_LEVEL_VIOLATION    broker minimum stop distance
BROKER_SPEC_INVALID     specification failed validation
SAFE_MODE               inconsistent state; managing only
```

A long run of `SPREAD_TOO_WIDE` on a venue means that venue's microstructure is
outside the strategy's operating envelope — not that the filter needs loosening.

## 6. Shadow mode

`MODE_SHADOW` computes every signal, evaluates every guard, sizes every position
and logs the whole decision — then submits nothing. The log shows:

```
XAU_RPB SHADOW: would send BUY lots=0.42 sl=2018.35 tp=0.00 - no order submitted
```

**Use shadow mode to verify the mirror against the research implementation on live
data before enabling trading.** That comparison is the practical test that the two
implementations agree outside of fixtures.

## 7. Restart recovery

On every init the EA enumerates open orders, matches them by **magic number and
comment prefix** (`XAU_RPB_V1`), and resumes management without re-entering:

```
XAU_RPB: recovered position ticket=12345 dir=LONG entry=2035.20 stop=2028.10
   - resuming management, no new entry
```

Two caveats worth knowing:

- The **signal-time ATR is not recoverable** from the broker. Trailing resumes on a
  freshly computed ATR rather than a fabricated one; trail distances immediately
  after a restart may differ slightly from an uninterrupted run.
- Finding **more than one** strategy position triggers `SAFE_MODE` (manage only,
  open nothing, alert), because the specification permits exactly one.

## 8. Kill switches

| Switch | Trigger | Clearing it |
|---|---|---|
| Daily loss stop | −1.5% from day-start equity | Automatic at the next server day |
| Weekly loss stop | −3.0% from week-start equity | Automatic at the next server week |
| Soft drawdown | −5.0% from peak | Automatic when equity recovers |
| Hard drawdown | −9.0% from peak | **Manual only** |
| Safe mode | Inconsistent state | Manual, after resolving the cause |

The hard kill **latches**: recovering equity does not re-enable trading. Resetting
it requires an operator identity and should follow an actual review of why the
drawdown happened. Removing the EA from the chart also clears in-memory state —
which is not a reset procedure, it is losing the state.

None of these liquidate. Open positions keep their broker-side stops.

## 9. Signal-parity verification

1. Copy `mt4/Include/xau_rpb/` → `MQL4/Include/xau_rpb/`
2. Copy `mt4/tests/XauRpbParityHarness.mq4` → `MQL4/Scripts/`
3. Copy `data/fixtures/xau_rpb/*.csv` → `MQL4/Files/`
4. Run the script once per scenario, setting `InpScenario` to each of
   `trend_up`, `trend_down`, `range`, `regime_flip`, `volatility_shock`
5. Copy the resulting `*.actual` files back into `data/fixtures/xau_rpb/`
6. Run:

```bash
uv run pytest tests/parity -v
```

Until step 6 passes, the MQL4 implementation is **unverified** against the
reference, and the parity tests will say so in their skip messages.

## 10. Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| `no symbol ... resolved to a valid spec` | Broker uses a different name | Add it to `InpSymbolAliases` |
| `invalid broker specification` | Market Watch entry not fully loaded | Open the symbol in Market Watch, restart the EA |
| `insufficient H1 history` | Fewer than ~510 H1 bars | Download history (F2 → History Center) |
| No trades ever | Check `reject_reason` counts in telemetry | Usually spread or session; both are working as specified |
| Everything `SPREAD_TOO_WIDE` | Venue spread is wide relative to ATR | Venue is outside the operating envelope; do not loosen the filter to force trades |
| `ORDER_REJECTED error=130` | Invalid stops vs `MODE_STOPLEVEL` | Terminal error by design — the EA will not widen the stop |
| `ORDER_REJECTED error=134` | Not enough money | Reduce risk or fund the account; the EA will not shrink the stop |
| Backtest sessions differ from live | Tester time handling | Set `InpAutoDetectOffset = false` and an explicit offset |

## 11. Exporting history from this machine's MT4

Verified working 2026-08-31. The exporter reads MT4's `.hst` files directly — the
terminal does not need to be closed, and nothing is written into it.

```bash
python scripts/export_mt4_history.py --list
```

```bash
python scripts/export_mt4_history.py --symbol XAUUSD --period 15 --out data/market --assumed-spread-points 25
```

Two things it deliberately makes loud:

- **Timestamps are broker server time, not UTC.** They are exported unchanged and
  the offset is recorded in the sidecar. Pass `--broker-offset us-dst` downstream
  (the default) for IC Markets-style servers.
- **`.hst` files carry no per-bar spread** — the value is always 0. The exporter
  writes a modelled constant and records `spread_source: MODELLED CONSTANT` in the
  sidecar so no report can mistake it for an observed spread.

Each export writes a `.meta.json` sidecar (bars, range, digits, sha256, spread
source). The CSVs are gitignored; the sidecars are tracked, so any result stays
traceable to the data that produced it.

Datasets found on this machine:

| Data folder | Bars | Range | Span |
|---|---|---|---|
| `1DAFD9A7…` (MT4 IC Markets) | 448,172 | 2004-06-11 → 2024-01-09 | **19.58 y** |
| `5D49F47D…` (MT4 IC Markets Global) | 27,636 | 2025-04-30 → 2026-06-30 | 1.17 y |

## 12. Research pipeline (Python side)

```bash
uv run python -m research.validation.cli data-quality --data <M15.csv>
uv run python -m research.validation.cli baseline     --data <M15.csv>
uv run python -m research.validation.cli sensitivity  --data <M15.csv>
uv run python -m research.validation.cli walk-forward --data <M15.csv>
uv run python -m research.validation.cli monte-carlo  --data <M15.csv>
uv run python -m research.validation.cli cost-stress  --data <M15.csv>
uv run python -m research.validation.cli full         --data <M15.csv>
```

Every command requires real market data and will not invent a dataset. `full` ends
with the frozen acceptance gates and exits non-zero on `REJECTED`.

## 13. Tests

```bash
uv run pytest tests/unit/strategy tests/unit/validation tests/leakage tests/parity
```
