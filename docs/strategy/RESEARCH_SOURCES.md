# XAU_RPB — Research Sources and Intellectual-Property Record

Mandate §4 requires a record of every external repository studied, what was taken
from it, and its licence status.

**Summary: no third-party source code was copied into this repository.** Every
module under `research/strategies/xau_rpb/`, `research/validation/`,
`mt4/Include/xau_rpb/` and `mt4/Experts/XauRpbEA.mq4` is an independent
implementation written against `XAUUSD_RPB_SPEC.md`. External projects were read
as *research references* — for algorithm structure, failure modes and risk
controls — not as code to reuse.

That choice is deliberate even where a licence would have permitted reuse: clean
ownership, one consistent architecture, and complete test coverage are worth more
here than the time a copy-paste would have saved.

## Repositories studied

Licence status is **as reported by the source audit** (cut-off 2026-08-30) and has
not been independently re-verified against the GitHub API by this implementation.
Because nothing was copied, the licence status is informational rather than load
bearing. Re-verify before any future decision that would depend on it.

| Repository | Language | Licence (per audit) | Concept studied | Code reused? | Why |
|---|---|---|---|---|---|
| `ilahuerta-IA/backtrader-pullback-window-xauusd` | Python / Backtrader | MIT (LICENSE present) | The four-phase pullback→breakout state machine; ATR-based stops; the idea of a bounded breakout window | **No** | The state-machine *shape* is the useful contribution. Its parameters (EMA 1/14/18/24, SL 2.5 ATR, TP 12 ATR, 3-bar pullback, 2-bar window) are treated as research seeds to be re-derived, not constants to inherit — see "Corrections" below. |
| `yulz008/GOLD_ORB` | MQL5 / MT5 | Not detected | Risk architecture: percent-of-equity sizing, max-equity-drawdown limit, losing-streak control, virtual equity, new-bar-only evaluation | **No** | MQL5, no detected licence, and calibrated around a specific broker server hour. The risk *discipline* was worth learning; the code was not usable and its `01:02` server-time anchor is an anti-pattern this spec explicitly rejects (§11). |
| `GimsDev/XAUUSD-Breakout-EA` | MQL4 / MT4 | README claims MIT; API does not detect one | Minimal consolidation-breakout structure in MQL4 | **No** | Licence ambiguity alone rules out reuse. Read for MQL4 idiom only. |
| `GimsDev/-XAUUSD-USDJPY-ATR-Scalper-EA` | MQL4 / MT4 | README claims MIT; API does not detect one | H1 EMA50/200 regime filter feeding a lower-timeframe trigger | **No** | The H1→LTF context/trigger separation informed §2 and §4. Its fixed-lot base is exactly what §7 forbids. |
| `yunming888/MT4-Gold-Pivot-EA` | MQL4 / MT4 | Not detected | Multi-factor quality score; risk reduction after consecutive losses | **No** | Studied as a *cautionary* example: 149% ROI alongside 37.6% max drawdown, an explicitly "winning" `.set` file, and no published period, PF, OOS or walk-forward. A textbook multiple-testing risk. |
| `kaksuli/EA` | MQL4 | Apache-2.0 | General EA architecture | **No** | Apache-2.0 would have permitted reuse. Rejected on engineering grounds: a very large DMI/RSI/StdDev/ATR parameter space is a large overfitting surface. |
| `frkn2076/XAUUSD-Forex` | MQL4 / MT4 | Not detected | — | **No** | **Explicitly excluded.** Opens successive positions against an adverse move (up to ten tickets). This is averaging/grid; §1 and §7.2 prohibit it. Studied only to characterize the tail risk being avoided. |
| `omidhaddadi/MT4_XAUUSD` | MQL4 / MT4 | Not detected | — | **No** | Insufficient documented evidence to be useful. |
| Random-Forest MT5 projects (various) | MQL5 / Python | Various | — | **No** | Out of scope: §1 prohibits machine-learned directional prediction in V1. |

## Corrections applied to the source audit

Reading the audit as a specification rather than as ground truth surfaced two
substantive errors. Both are fixed here, and both are pinned by tests.

**1. Tick-size semantics — a 100× position-sizing error.** The audit's sample
`CalculateRiskLots` computes

```
double tickSizePrice = s.tickSizePoints * s.point;
```

treating `MODE_TICKSIZE` as a count of points. It is not: MT4's `MODE_TICKSIZE`
is the minimal **price** increment (0.01 on a 2-digit XAUUSD). Multiplying by
`Point` understates every position by a factor of `1/Point` — 100× on a 2-digit
gold feed. `tests/unit/strategy/test_sizing.py` pins the correct economics
(0.5 lots of a 100 oz contract risking exactly $500 across a $10 stop).

**2. Breakout reference construction.** A literal reading of "extend the breakout
reference with each new bar" makes the *recovery bar* — the classic
pullback-breakout entry bar — structurally unable to trigger, because its own high
is folded into the level it must exceed. The specification (§5.3) freezes the
reference at the pullback structure and evaluates the recovery bar directly. This
was found by a state-machine test, not by inspection.

## Metrics from external repositories

Every performance figure in the source audit is **evidence to investigate, not a
result to inherit**. Specifically:

- `ilahuerta` reports +44.75% / PF 1.64 / Sharpe 0.892 / 5.81% max DD over 175
  trades (Jul 2020 – Jul 2025). The audit itself corrects the repository's
  "8.95% average annual return" to an implied **CAGR of ~7.61%**, and notes there
  is no documented independent OOS test, walk-forward or Monte Carlo, and that the
  short side was disabled pending optimization.
- `yunming888` reports 149% ROI with 37.6% max drawdown over 661 trades, with no
  published period, PF, CAGR, OOS or walk-forward, and an explicitly selected
  "winning configuration".

**No figure from either source is reproduced as a property of this
implementation.** This strategy's own numbers can only come from
`research/validation/`, run on real data, under the frozen gates.

## Academic references

Concepts used, not code:

- Bailey, Borwein, López de Prado & Zhu — *Probability of Backtest Overfitting*
  (CSCV) and the *Deflated Sharpe Ratio*. Implemented independently in
  `research/validation/overfitting.py` from the published definitions.
- Moskowitz, Ooi & Pedersen — time-series momentum in liquid futures. Used only as
  the economic-plausibility argument for choosing a trend/pullback family over a
  contrarian grid; it is **not** evidence that this specific M15 XAUUSD
  configuration has an edge.

## Standing rule

If any third-party code is ever introduced, this document must record the file,
the upstream commit, the verified licence text, and the reason reuse was preferred
to reimplementation — **before** the code is merged.
