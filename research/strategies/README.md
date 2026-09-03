# research/strategies — strategy compositions

## `xau_rpb/` — XAUUSD Regime-Filtered Pullback → Breakout (`XAU_RPB_V1.0.0`)

The **canonical** implementation of the strategy frozen in
[`docs/strategy/XAUUSD_RPB_SPEC.md`](../../docs/strategy/XAUUSD_RPB_SPEC.md).
`mt4/Experts/XauRpbEA.mq4` is its mirror, held to it by `tests/parity/`.

> **Status: RESEARCH ONLY.** The strategy has never been measured — no XAUUSD
> market data exists in this repository, so every acceptance gate is unevaluated.
> See [`RESEARCH_REPORT.md`](../../docs/strategy/RESEARCH_REPORT.md).

| Module | Responsibility |
|---|---|
| `types.py` | Value objects: `Bar`, `BrokerSpec`, `Trade`, enums |
| `config.py` | Parameters in the four categories of spec §14; config hashing |
| `indicators.py` | EMA, ATR, ADX, Efficiency Ratio, ATR percentile (exact spec definitions) |
| `regime.py` | H1 regime engine (spec §4) |
| `state_machine.py` | M15 pullback → breakout state machine (spec §5) |
| `scoring.py` | 7-factor signal score, max 9 (spec §6) |
| `sizing.py` | Broker-aware position sizing (spec §7.1) |
| `risk_limits.py` | Daily / weekly / drawdown kill switches (spec §7.2) |
| `sessions.py` | Broker time → UTC → DST-aware sessions (spec §11) |
| `news.py` | Frozen-CSV high-impact blackout (spec §12) |
| `backtest.py` | Event-driven simulation with an explicit cost model |
| `data.py` | CSV loading and the spec §32 data-quality report |
| `parity.py` | Signal-parity fixtures and goldens |

Validation and robustness tooling lives in [`research/validation/`](../validation/).

```bash
uv run python -m research.validation.cli full --data <XAUUSD_M15.csv>
```
